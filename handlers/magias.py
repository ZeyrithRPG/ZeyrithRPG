"""
Fase 2.5 — Magias no combate. Usa os dados reais da aba Magia e Habilidades,
dano derivado da Curva Mestra (mesma fórmula do dano de arma, só multiplicador
diferente) — sem matemática paralela, como já fechamos.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.connection import get_session
from db.models import Player, Magia, Monstro, CurvaMestra, HabilidadeAtiva
from game.combat import resolver_ataque
from game.ui_utils import barra as _barra

ICONE_ELEMENTO = {
    "Fogo": "🔥", "Gelo": "❄️", "Raio": "⚡", "Sombra": "🌑", "Luz": "✨", "Arcano": "🔮",
}
CUSTO_POR_GRAU = {"Basico": 0.15, "Avancado": 0.4, "Mestre": 0.65}


async def menu_magias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    if not player.em_combate_monstro_id:
        session.close()
        await query.answer("Só dá pra conjurar durante um combate.", show_alert=True)
        return

    await query.answer()

    mana_max = player.mana_max or 0
    magias_disponiveis = session.query(Magia).filter(
        Magia.nivel_minimo <= (player.nivel or 1)
    ).order_by(Magia.nivel_minimo).all()

    hab_classe = session.query(HabilidadeAtiva).filter_by(classe_id=player.classe_id).first() if player.classe_id else None
    tem_hab_magica = hab_classe and hab_classe.tipo_acao == "Mágica"

    if (not magias_disponiveis and not tem_hab_magica) or mana_max == 0:
        session.close()
        await query.answer("Você não conhece nenhuma magia ainda.", show_alert=True)
        return

    linhas = [f"🔷 Mana: {player.mana_atual}/{mana_max}\n"]
    botoes = []

    if tem_hab_magica:
        custo_hab = hab_classe.custo_recurso
        pode_pagar_hab = player.mana_atual >= custo_hab or ("conjurador" in (player.classe.nome if player.classe else "").lower())
        pacto_label = " 🩸(Pacto)" if (player.mana_atual < custo_hab and "conjurador" in (player.classe.nome if player.classe else "").lower()) else ""
        linhas.append(f"⭐ *{hab_classe.habilidade_nome}* (Habilidade Inicial) — custo {custo_hab} mana{pacto_label}")
        if pode_pagar_hab:
            botoes.append([InlineKeyboardButton(f"✨ {hab_classe.habilidade_nome}", callback_data="hab_ativa_magica")])

    for m in magias_disponiveis:
        custo_real = round(mana_max * CUSTO_POR_GRAU.get(m.grau, 0.15))
        icone = ICONE_ELEMENTO.get(m.elemento, "✨")
        pode_pagar = player.mana_atual >= custo_real
        linhas.append(f"{icone} *{m.nome}* ({m.grau}) — custo {custo_real} mana{'  ❌' if not pode_pagar else ''}")
        if pode_pagar:
            botoes.append([InlineKeyboardButton(f"{icone} {m.nome}", callback_data=f"magia_{m.id}")])
    botoes.append([InlineKeyboardButton("⬅️ Voltar ao combate", callback_data="voltar_combate")])

    session.close()
    await query.edit_message_text(
        "✨ *Suas Magias*\n\n" + "\n".join(linhas),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(botoes),
    )


OPOSICAO_ELEMENTAL = {
    "Fogo": "Gelo",
    "Gelo": "Fogo",
    "Luz": "Sombra",
    "Sombra": "Luz",
    "Raio": "Arcano",
    "Arcano": "Raio",
}

PALAVRAS_CHAVE_ELEMENTO = {
    "Fogo": ["fogo", "chamas", "magma", "vulcânico", "vulcanico", "incandescente", "lava", "queimadura"],
    "Gelo": ["gelo", "glacial", "frio", "gélido", "gelido", "neve", "geada"],
    "Luz": ["luz", "sagrado", "radiante", "solar", "aurora", "reluzente"],
    "Sombra": ["sombra", "escuridão", "escuridao", "abissal", "necró", "necro", "morte", "vazio", "sem-voz", "morto-vivo", "esqueleto", "sangue"],
    "Raio": ["raio", "elétrico", "eletrico", "trovão", "trovao", "tempestade", "choque"],
    "Arcano": ["arcano", "dimensional", "cósmico", "cosmico", "místico", "mistico", "estelar", "fenda"],
}


def detectar_elemento_monstro(monstro) -> str | None:
    """Identifica a afinidade elemental do monstro pelo seu nome, fraqueza, golpes ou lore."""
    if not monstro:
        return None
    fraqueza = (monstro.fraqueza or "").lower()
    for elem, oposto in OPOSICAO_ELEMENTAL.items():
        if elem.lower() in fraqueza or f"vulnerável a {elem.lower()}" in fraqueza:
            # Se é vulnerável a Gelo, a afinidade dele é o oposto (Fogo)
            return oposto

    texto_completo = f"{monstro.nome} {monstro.golpe_especial or ''} {monstro.efeito_mecanico or ''} {monstro.motivacao or ''}".lower()
    for elem, chaves in PALAVRAS_CHAVE_ELEMENTO.items():
        if any(ch in texto_completo for ch in chaves):
            return elem
    return None


def resolver_multiplicador_elemental(elemento_magia: str, monstro, nome_magia: str = "") -> tuple[float, str]:
    """
    Roda Elemental da planilha (Magia e Habilidades R5-R8):
    - Oposto: +50% de dano (Fogo <-> Gelo, Luz <-> Sombra, Raio <-> Arcano)
    - Igual: -50% de dano
    """
    if "Ruptura Dimensional" in nome_magia or "Colapso da Realidade" in nome_magia:
        return 1.0, ""

    elem_monstro = detectar_elemento_monstro(monstro)
    fraqueza_txt = (monstro.fraqueza or "").lower()

    # Checa se fraqueza explicitamente cita o elemento
    if elemento_magia and elemento_magia.lower() in fraqueza_txt:
        return 1.5, " ⚡ Vantagem Elemental (+50% de dano!)"

    if not elem_monstro or not elemento_magia:
        return 1.0, ""

    if elem_monstro == elemento_magia:
        return 0.5, " 🛡️ Resistência Elemental (-50% de dano)"
    elif OPOSICAO_ELEMENTAL.get(elemento_magia) == elem_monstro:
        return 1.5, " ⚡ Vantagem Elemental (+50% de dano!)"

    return 1.0, ""


async def conjurar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    magia_id = int(query.data.split("_")[1])

    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    magia = session.get(Magia, magia_id)
    monstro = session.get(Monstro, player.em_combate_monstro_id) if player.em_combate_monstro_id else None

    if magia is None or monstro is None or player.em_combate_hp_monstro is None:
        session.close()
        await query.answer()
        await query.edit_message_text(
            "Esse combate não está mais ativo.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]),
        )
        return

    curva = session.query(CurvaMestra).filter_by(nivel=player.nivel or 1).first()
    mana_max = player.mana_max or 0
    custo_real = round(mana_max * CUSTO_POR_GRAU.get(magia.grau, 0.15))

    if player.mana_atual < custo_real:
        session.close()
        await query.answer("Mana insuficiente.", show_alert=True)
        return

    await query.answer()

    player.mana_atual -= custo_real
    atq_bonus_jogador = (curva.atq_bonus if curva else 2)

    # Dano mágico sem atributo INT (V1.0)
    from game.atributos import calcular_defesa_total, calcular_critico_chance
    from game.combat import calcular_dano_magico
    from game.corrupcao import modificador_dano_corrupcao

    dano_base_magia = magia.dano or 6

    # Roda elemental (+50% oposto, -50% igual)
    mult_elem, tag_elem = resolver_multiplicador_elemental(magia.elemento, monstro, magia.nome)
    # Bônus de corrupção Estágio III (+15%)
    mult_corr = modificador_dano_corrupcao(player)
    from game.talentos import verificar_lanca_purificacao
    bonus_purif, ignora_res_inq = verificar_lanca_purificacao(player, monstro, session)
    defesa_alvo = 0 if ignora_res_inq else monstro.defesa
    dano_calculado = calcular_dano_magico(dano_base_magia, mult_magia=1.0, mult_elemental=mult_elem, mult_corrupcao=mult_corr) + bonus_purif

    res = resolver_ataque(atq_bonus_jogador, defesa_alvo, dano_calculado, bonus_critico_pct=calcular_critico_chance(player))
    linhas = [f"{ICONE_ELEMENTO.get(magia.elemento,'✨')} Você conjura *{magia.nome}*!"]
    if res.acertou:
        player.em_combate_hp_monstro -= res.dano
        linhas.append(f"💥 Acerto{' CRÍTICO' if res.critico else ''}: *{res.dano}* de dano mágico.{tag_elem}")
    else:
        linhas.append("💨 A magia erra o alvo.")

    if player.em_combate_hp_monstro <= 0:
        from handlers.aventura import _vitoria
        await _vitoria(session, query, player, monstro, linhas)
        return

    # Contra-ataque do monstro contra Defesa Total calculada dinamicamente
    defesa_jogador = calcular_defesa_total(player, session)
    res_m = resolver_ataque(monstro.atq_bonus, defesa_jogador, monstro.dano)
    if res_m.acertou:
        player.hp_atual -= res_m.dano
        linhas.append(f"💥 {monstro.nome} contra-ataca: *{res_m.dano}* de dano.")
    else:
        linhas.append(f"💨 {monstro.nome} errou.")

    if player.hp_atual <= 0:
        from handlers.aventura import _derrota
        await _derrota(session, query, player, linhas, monstro)
        return

    session.commit()
    hp_m, hp_m_max = player.em_combate_hp_monstro, monstro.hp
    hp_j, hp_j_max = player.hp_atual, player.hp_max
    mana_atual = player.mana_atual
    from handlers.aventura import _botoes_combate
    markup = _botoes_combate(session, player, monstro)
    session.close()
    await query.edit_message_text(
        "\n".join(linhas) + f"\n\n❤️ {monstro.nome}: {hp_m}/{hp_m_max}\n"
        f"🧍 Você: {hp_j}/{hp_j_max}  ·  🔷 Mana: {mana_atual}/{mana_max}",
        parse_mode="Markdown",
        reply_markup=markup,
    )


async def habilidade_ativa_magica_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executa a habilidade ativa mágica inicial da classe do jogador."""
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    monstro = session.get(Monstro, player.em_combate_monstro_id) if player and player.em_combate_monstro_id else None
    if monstro is None or player.em_combate_hp_monstro is None:
        session.close()
        await query.edit_message_text(
            "Esse combate não está mais ativo.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return

    linhas = []

    # 1) Tick de efeitos ativos e mutações
    from game.efeitos import aplicar_dano_periodico, ICONE_EFEITO
    from game.combat import dano_passivo_turno_mutacao, resistencia_dot_mutacao
    dano_gelo = dano_passivo_turno_mutacao(player)
    if dano_gelo > 0:
        player.em_combate_hp_monstro = max(0, player.em_combate_hp_monstro - dano_gelo)
        linhas.append(f"❄️ *Presença Gélida:* Geada causa {dano_gelo} de dano passivo em {monstro.nome}.")

    if player.em_combate_efeito_monstro and player.em_combate_efeito_monstro_turnos:
        dano_dot = aplicar_dano_periodico(player.em_combate_efeito_monstro)
        if dano_dot:
            player.em_combate_hp_monstro -= dano_dot
            icone_ef = ICONE_EFEITO.get(player.em_combate_efeito_monstro, "🔸")
            linhas.append(f"{icone_ef} {player.em_combate_efeito_monstro} causa {dano_dot} de dano em {monstro.nome}.")
        player.em_combate_efeito_monstro_turnos -= 1
        if player.em_combate_efeito_monstro_turnos <= 0:
            player.em_combate_efeito_monstro = None
            player.em_combate_efeito_monstro_turnos = None

    if player.em_combate_efeito_jogador and player.em_combate_efeito_jogador_turnos:
        dano_dot = aplicar_dano_periodico(player.em_combate_efeito_jogador)
        if dano_dot:
            red_dot = resistencia_dot_mutacao(player, player.em_combate_efeito_jogador)
            if red_dot > 0:
                dano_dot = max(1, round(dano_dot * (1.0 - red_dot)))
            player.hp_atual -= dano_dot
            icone_ef = ICONE_EFEITO.get(player.em_combate_efeito_jogador, "🔸")
            linhas.append(f"{icone_ef} {player.em_combate_efeito_jogador} causa {dano_dot} de dano em você.")
        player.em_combate_efeito_jogador_turnos -= 1
        if player.em_combate_efeito_jogador_turnos <= 0:
            player.em_combate_efeito_jogador = None
            player.em_combate_efeito_jogador_turnos = None

    if player.em_combate_hp_monstro <= 0:
        from handlers.aventura import _vitoria
        await _vitoria(session, query, player, monstro, linhas)
        return
    if player.hp_atual <= 0:
        from handlers.aventura import _derrota
        await _derrota(session, query, player, linhas, monstro)
        return

    # 2) Execução da habilidade mágica ativa via dispatcher oficial
    from game.combat import executar_habilidade_ativa, resolver_ataque
    from game.atributos import calcular_defesa_total

    nome_classe = player.classe.nome if player.classe else ""
    res = executar_habilidade_ativa(
        classe_nome=nome_classe,
        jogador=player,
        alvo=monstro,
        nivel_habilidade=player.habilidade_ativa_nivel,
        session=session,
    )
    player.em_combate_turnos = (player.em_combate_turnos or 0) + 1

    if not res.sucesso:
        session.close()
        await query.answer(res.motivo_falha, show_alert=True)
        return

    pacto_txt = f" (🩸 Pacto: {res.hp_sacrificado} HP)" if res.hp_sacrificado > 0 else ""
    linhas.append(f"✨ Você conjura *{res.habilidade_nome}*! (Gasto: {res.recurso_gasto} {res.recurso_tipo}{pacto_txt})")

    if res.acertou:
        player.em_combate_hp_monstro -= res.dano
        linhas.append(f"💥 Conjurou com sucesso{' 💥 CRÍTICO!' if res.critico else '!'}: *{res.dano}* de dano mágico.")
        if res.cura > 0:
            linhas.append(f"🩸 Drenagem Vital restaurou *{res.cura}* do seu HP!")
        if res.efeito_descricao and "Drenagem" not in res.efeito_descricao:
            linhas.append(res.efeito_descricao)
    else:
        linhas.append(f"💨 {res.habilidade_nome} errou o alvo!")

    if player.em_combate_hp_monstro <= 0:
        from handlers.aventura import _vitoria
        await _vitoria(session, query, player, monstro, linhas)
        return

    # 3) Contra-ataque do monstro
    if player.em_combate_efeito_monstro == "Atordoado":
        linhas.append(f"💫 {monstro.nome} está atordoado e não pôde agir!")
        player.em_combate_efeito_monstro_turnos = (player.em_combate_efeito_monstro_turnos or 1) - 1
        if player.em_combate_efeito_monstro_turnos <= 0:
            player.em_combate_efeito_monstro = None
            player.em_combate_efeito_monstro_turnos = None
    else:
        defesa_jogador = calcular_defesa_total(player, session)
        res_m = resolver_ataque(monstro.atq_bonus, defesa_jogador, monstro.dano)
        if res_m.acertou:
            dano_m = res_m.dano
            if player.em_combate_efeito_jogador == "Proteção Radiante":
                dano_m = max(1, round(dano_m * 0.85))
                linhas.append("🛡️ Sua Proteção Radiante reduziu o dano sofrido!")
            player.hp_atual -= dano_m
            linhas.append(f"💥 {monstro.nome} contra-ataca: *{dano_m}* de dano.")
        else:
            linhas.append(f"💨 {monstro.nome} errou o ataque.")

    if player.hp_atual <= 0:
        from handlers.aventura import _derrota
        await _derrota(session, query, player, linhas, monstro)
        return

    session.commit()
    hp_m, hp_m_max = player.em_combate_hp_monstro, monstro.hp
    hp_j, hp_j_max = player.hp_atual, player.hp_max
    mana_atual, mana_max = player.mana_atual, player.mana_max
    nome_monstro, papel_monstro, nivel_monstro = monstro.nome, monstro.papel, monstro.nivel

    from handlers.aventura import _formata_efeito, _botoes_combate, ICONE_PAPEL
    icone_papel = ICONE_PAPEL.get(papel_monstro, "⚪")
    efeito_monstro_txt = _formata_efeito(player.em_combate_efeito_monstro, player.em_combate_efeito_monstro_turnos)
    efeito_jogador_txt = _formata_efeito(player.em_combate_efeito_jogador, player.em_combate_efeito_jogador_turnos)
    markup = _botoes_combate(session, player, monstro)
    session.close()

    await query.edit_message_text(
        f"{icone_papel} *{nome_monstro}* Nv.{nivel_monstro} ({papel_monstro}){efeito_monstro_txt}\n"
        f"❤️ {hp_m}/{hp_m_max}\n{_barra(hp_m, hp_m_max, cheio='🟥')}\n\n"
        + "\n".join(linhas) +
        f"\n\n🧍 Você{efeito_jogador_txt}\n❤️ {hp_j}/{hp_j_max}\n{_barra(hp_j, hp_j_max)}"
        + (f"\n⚡ Vigor: {player.vig_atual}/{player.vig_max}" if player.vig_max else "")
        + (f"\n🔷 Mana: {mana_atual}/{mana_max}" if mana_max else ""),
        parse_mode="Markdown",
        reply_markup=markup,
    )

