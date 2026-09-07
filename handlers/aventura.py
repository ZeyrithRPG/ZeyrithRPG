"""
Fase 2 — Aventura: explorar, encontrar monstro, combate.
Visual denso, com ícone em cada linha de informação (padrão Pixel Realm).
"""
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.connection import get_session
from db.models import Player, Local, Tier, CurvaMestra, Monstro
from game.exploracao import custo_vig_exploracao, rolar_exploracao
from game.combat import resolver_ataque, chance_fuga, verificar_pode_poupar
from game.efeitos import identificar_efeito, aplicar_dano_periodico, turnos_padrao, ICONE_EFEITO

ICONE_TIPO_LOCAL = {
    "Cidade": "🏰", "Estrada Perigosa": "🛤️", "Mina": "⛏️", "Dungeon": "🕸️",
    "Ruina": "🏛️", "Floresta Perigosa": "🌲", "Caverna": "🕳️",
    "Planicie Selvagem": "🌾", "Fenda": "🌋", "Campo de Batalha": "⚔️",
    "Pantano": "🐊", "Covil de Boss": "💀", "Ritual": "🔮", "Portal": "🌀",
}
ICONE_PAPEL = {"Comum": "⚪", "Elite": "🟣", "Boss": "🔴", "Cosmico": "⚫"}
BARRA_PERIGO = {1: "🟢", 2: "🟢", 3: "🟡", 4: "🟠", 5: "🔴"}


from game.ui_utils import barra as _barra


def _tier_numero(nome_tier, session):
    tiers = session.query(Tier).order_by(Tier.id).all()
    for i, t in enumerate(tiers, start=1):
        if t.nome == nome_tier:
            return i
    return 1


def _nome_do_tier(numero, session):
    tiers = session.query(Tier).order_by(Tier.id).all()
    if not tiers:
        return "Sucata Enferrujada"
    idx = max(0, min(numero - 1, len(tiers) - 1))
    return tiers[idx].nome


def _curva(session, nivel):
    return session.query(CurvaMestra).filter_by(nivel=nivel).first()


def _local_do_player(session, player):
    local = None
    if player.local_atual:
        local = session.query(Local).filter_by(nome=player.local_atual).first()
    if local is None:
        local = session.query(Local).filter_by(nome="Vila Inicial").first()
        if local is None:
            local = session.query(Local).order_by(Local.id).first()
        if local is not None:
            player.local_atual = local.nome
            session.commit()
    return local


# ---------- Menu Aventura ----------

async def menu_aventura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _redesenhar_menu_aventura(query, update)


async def _redesenhar_menu_aventura(query, update):
    """Corpo de menu_aventura sem chamar query.answer() -- usado tanto pelo callback
    normal quanto por handlers que já responderam o clique (ex: descansar_handler),
    porque o Telegram só aceita 1 answer() por clique (a segunda chamada é ignorada
    ou pode falhar -- ver ARMADILHAS no resumo do projeto)."""
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    local = _local_do_player(session, player)
    icone_local = ICONE_TIPO_LOCAL.get(local.tipo, "📍")
    barra_perigo = BARRA_PERIGO.get(local.perigo, "🟡") * local.perigo + "⬛" * (5 - local.perigo)
    custo = custo_vig_exploracao(local.perigo)

    vig_atual, vig_max = player.vig_atual, player.vig_max
    subtitulo = local.tipo
    if local.cidade_proxima and local.cidade_proxima != local.nome:
        subtitulo += f" · perto de {local.cidade_proxima}"

    texto = (
        f"{icone_local} *{local.nome}*\n"
        f"_{subtitulo}_\n\n"
        f"{local.descricao}\n\n"
        f"⚠️ Perigo: {barra_perigo} ({local.perigo}/5)\n"
        f"⚡ Vigor: {vig_atual}/{vig_max}\n"
        f"{_barra(vig_atual, vig_max)}\n\n"
        f"🔍 Custo pra explorar aqui: *{custo} VIG*"
    )
    botoes = [[InlineKeyboardButton("🔍 Explorar", callback_data="explorar")]]
    from game.descanso import pode_descansar
    if pode_descansar(session, player):
        botoes.append([InlineKeyboardButton("😴 Descansar", callback_data="descansar")])
    botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")])
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def descansar_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from game.descanso import descansar, ErroDescanso

    query = update.callback_query
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    try:
        custo = descansar(session, player)
        await query.answer(f"😴 Você descansou! HP/Vigor/Mana restaurados. (-{custo} Ouro)", show_alert=True)
    except ErroDescanso as e:
        await query.answer(f"❌ {e}", show_alert=True)
    session.close()
    await _redesenhar_menu_aventura(query, update)


# ---------- Explorar ----------

async def explorar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    local = _local_do_player(session, player)

    custo = custo_vig_exploracao(local.perigo)
    if player.vig_atual < custo:
        vig_atual, vig_max = player.vig_atual, player.vig_max
        session.close()
        await query.edit_message_text(
            f"⚡ *Vigor insuficiente* pra explorar aqui.\n\n"
            f"⚡ Vigor: {vig_atual}/{vig_max}\n"
            f"🔍 Precisa de: {custo} VIG\n\n"
            "_(Volte a uma cidade pra descansar e recuperar Vigor.)_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("🗺️ Ir ao Mapa", callback_data="menu_mapa"),
                    InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status"),
                ]
            ]),
        )
        return

    player.vig_atual -= custo
    from game.relogio import avancar_tempo
    avancar_tempo(player)

    from game.eventos import evento_aleatorio
    evento = evento_aleatorio(session, player)
    if evento:
        session.commit()
        nome_local, vig_atual, vig_max = local.nome, player.vig_atual, player.vig_max
        icone_local = ICONE_TIPO_LOCAL.get(local.tipo, "📍")
        nome_evento, categoria_evento = evento.nome, evento.categoria
        session.close()
        await query.edit_message_text(
            f"{icone_local} *{nome_local}*\n\n"
            f"🌫️ *{nome_evento}*\n_{categoria_evento}_\n\n"
            f"⚡ Vigor: {vig_atual}/{vig_max}\n{_barra(vig_atual, vig_max)}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔍 Explorar de novo", callback_data="explorar")],
                 [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_aventura")]]
            ),
        )
        return

    resultado = rolar_exploracao(local.perigo)
    icone_local = ICONE_TIPO_LOCAL.get(local.tipo, "📍")

    if resultado == "nada":
        session.commit()
        nome_local, vig_atual, vig_max = local.nome, player.vig_atual, player.vig_max
        session.close()
        await query.edit_message_text(
            f"{icone_local} *{nome_local}*\n\n"
            f"🌫️ Nada de interessante dessa vez. (-{custo} VIG)\n\n"
            f"⚡ Vigor: {vig_atual}/{vig_max}\n{_barra(vig_atual, vig_max)}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔍 Explorar de novo", callback_data="explorar")],
                 [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return

    if resultado == "achado":
        achado_ouro = random.randint(5, 20) * player.tier_mais_alto_alcancado
        player.ouro += achado_ouro
        session.commit()
        ouro_total, vig_atual, vig_max = player.ouro, player.vig_atual, player.vig_max
        session.close()
        await query.edit_message_text(
            f"✨ *Achado raro!*\n\n"
            f"Você encontra {achado_ouro} de Ouro escondido no caminho.\n\n"
            f"💰 Ouro total: {ouro_total}\n"
            f"⚡ Vigor: {vig_atual}/{vig_max}\n{_barra(vig_atual, vig_max)}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔍 Explorar de novo", callback_data="explorar")],
                 [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return

    tier_num = player.tier_mais_alto_alcancado
    papel = {"comum": "Comum", "elite": "Elite", "boss": "Boss", "ameaca_sup": "Elite"}[resultado]
    if resultado == "ameaca_sup":
        tier_num = min(tier_num + 1, 14)

    tier_nome = _nome_do_tier(tier_num, session)
    from game.relogio import monstro_disponivel_agora
    candidatos = session.query(Monstro).filter_by(tier=tier_nome, papel=papel).all()
    candidatos_no_periodo = [m for m in candidatos if monstro_disponivel_agora(m, player.hora_do_mundo)]
    if candidatos_no_periodo:
        candidatos = candidatos_no_periodo
    if not candidatos:
        candidatos = session.query(Monstro).filter_by(tier=tier_nome, papel="Comum").all()
    if not candidatos:
        candidatos = session.query(Monstro).filter_by(tier=tier_nome).all()
    if not candidatos:
        session.commit()
        nome_local, vig_atual, vig_max = local.nome, player.vig_atual, player.vig_max
        session.close()
        await query.edit_message_text(
            f"{icone_local} *{nome_local}*\n\n🌫️ Você ouve algo à distância, mas nada aparece.\n\n"
            f"⚡ Vigor: {vig_atual}/{vig_max}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔍 Explorar de novo", callback_data="explorar")],
                 [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return
    monstro = random.choice(candidatos)

    player.em_combate_monstro_id = monstro.id
    from game.codex import registrar_encontro
    registrar_encontro(session, player, monstro.id)
    player.em_combate_turnos = 0
    player.em_combate_proficiencia_ganha = 0
    player.em_combate_hp_monstro = monstro.hp
    session.commit()

    icone_papel = ICONE_PAPEL.get(monstro.papel, "⚪")
    vig_atual, vig_max = player.vig_atual, player.vig_max
    mana_atual, mana_max = player.mana_atual, player.mana_max
    from game.ui_utils import esc_md
    m_nome = esc_md(monstro.nome)
    m_papel = esc_md(monstro.papel)
    l_nome = esc_md(local.nome)
    m_mot = esc_md(monstro.motivacao) if monstro.motivacao else ""
    m_golpe = esc_md(monstro.golpe_especial)

    texto = (
        f"⚔️ *COMBATE INICIADO*\n"
        f"{icone_local} {l_nome}\n\n"
        f"{icone_papel} *{m_nome}* — Nv.{monstro.nivel} ({m_papel})\n"
        f"❤️ {monstro.hp}/{monstro.hp}\n{_barra(monstro.hp, monstro.hp, cheio='🟥')}\n\n"
    )
    if m_mot:
        texto += f"_{m_mot}_\n\n"
    texto += (
        f"🗡️ Golpe: {m_golpe}\n\n"
        f"⚡ Seu Vigor: {vig_atual}/{vig_max}"
        + (f"\n🔷 Mana: {mana_atual}/{mana_max}" if mana_max else "")
    )
    markup = _botoes_combate(session, player, monstro)
    session.close()
    await query.edit_message_text(
        texto, parse_mode="Markdown",
        reply_markup=markup,
    )


def _botoes_combate(session, player, monstro):
    """Gera o teclado oficial de combate V1.0 com botão de habilidade ativa da classe."""
    botoes = [[InlineKeyboardButton("⚔️ Atacar", callback_data="atacar")]]
    from db.models import HabilidadeAtiva
    hab = session.query(HabilidadeAtiva).filter_by(classe_id=player.classe_id).first() if player and player.classe_id else None
    if hab:
        icone = "🔷" if hab.recurso_tipo == "Mana" else "⚡"
        custo = hab.custo_recurso or 0
        rotulo = f"{icone} {hab.habilidade_nome} ({custo} {hab.recurso_tipo})"
        if hab.tipo_acao == "Física":
            botoes[0].append(InlineKeyboardButton(rotulo, callback_data="hab_ativa_fisica"))
        else:
            botoes[0].append(InlineKeyboardButton(rotulo, callback_data="hab_ativa_magica"))

    hp_m = player.em_combate_hp_monstro if (player and player.em_combate_hp_monstro is not None) else getattr(monstro, "hp", 1)
    if monstro and verificar_pode_poupar(monstro, hp_m, monstro.hp):
        botoes.append([InlineKeyboardButton("🕊️ Poupar", callback_data="poupar")])
    if player and player.mana_max:
        if len(botoes) > 1 and botoes[-1][0].callback_data == "poupar":
            botoes[-1].append(InlineKeyboardButton("📖 Grimório", callback_data="menu_magias"))
        else:
            botoes.append([InlineKeyboardButton("📖 Grimório", callback_data="menu_magias")])
    botoes.append([InlineKeyboardButton("🏃 Fugir", callback_data="fugir")])
    return InlineKeyboardMarkup(botoes)


# ---------- Combate ----------

async def atacar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    monstro = session.get(Monstro, player.em_combate_monstro_id) if player.em_combate_monstro_id else None
    if monstro is None or player.em_combate_hp_monstro is None:
        session.close()
        await query.edit_message_text(
            "Esse combate não está mais ativo.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return
    player.em_combate_turnos = (player.em_combate_turnos or 0) + 1
    tier_jogador = session.query(Tier).filter(
        Tier.id == player.tier_mais_alto_alcancado
    ).first()
    curva = _curva(session, player.nivel)

    dano_jogador_base = tier_jogador.dano_comum if tier_jogador else 4
    atq_bonus_jogador = curva.atq_bonus if curva else 2
    icone_papel = ICONE_PAPEL.get(monstro.papel, "⚪")

    linhas = []

    # --- 1) tick dos efeitos ativos (dano periodico de Sangramento/Queimadura/Veneno) e mutações ---
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

    # checa se o efeito periodico ja resolveu o combate
    if player.em_combate_hp_monstro <= 0:
        await _vitoria(session, query, player, monstro, linhas)
        return
    if player.hp_atual <= 0:
        await _derrota(session, query, player, linhas, monstro)
        return

    # --- 2) ataque do jogador ---
    from db.models import PlayerInventario, Classe, Arma, Armadura
    from game.atributos import calcular_defesa_total, calcular_critico_chance
    from game.combat import calcular_modificador_empunhadura, calcular_dano_fisico
    from game.corrupcao import modificador_dano_corrupcao

    defesa_jogador = calcular_defesa_total(player, session)

    arma_equipada = (
        session.query(PlayerInventario)
        .filter_by(player_id=player.id, tipo_item="arma", equipado=True)
        .first()
    )
    arma_obj = session.query(Arma).filter_by(id=arma_equipada.item_ref_id).first() if arma_equipada and arma_equipada.item_ref_id else None

    # Verifica se slot secundário (Escudo) está ocupado
    escudo_equipado = (
        session.query(PlayerInventario)
        .join(Armadura, PlayerInventario.item_ref_id == Armadura.id)
        .filter(
            PlayerInventario.player_id == player.id,
            PlayerInventario.tipo_item == "armadura",
            PlayerInventario.equipado == True,
            Armadura.slot == "Escudo"
        )
        .first()
    )
    mult_empunhadura, desc_empunhadura = calcular_modificador_empunhadura(
        arma_obj.tipo if arma_obj else "",
        escudo_equipado is not None
    )
    mult_corr = modificador_dano_corrupcao(player)

    dano_base = round(arma_obj.dano_comum * (arma_obj.mod_variacao or 1.0)) if arma_obj and arma_obj.dano_comum else (tier_jogador.dano_comum if tier_jogador else 4)
    if arma_equipada and getattr(arma_equipada, "danificado", False):
        dano_base = round(dano_base * 0.5)
    if getattr(player, "debuff_ativo", None) == "Tremor nos Braços":
        dano_base = max(1, dano_base - 1)
    tipo_arma_str = arma_obj.tipo if arma_obj else ""
    dano_jogador_calculado = calcular_dano_fisico(
        dano_base,
        mult_empunhadura=mult_empunhadura,
        mult_corrupcao=mult_corr,
        player=player,
        tipo_arma=tipo_arma_str,
        monstro=monstro,
        session=session,
    )

    from game.combat import bonus_ataque_mutacao
    atq_bonus_jogador += bonus_ataque_mutacao(player, tipo_arma=tipo_arma_str, hora_do_mundo=getattr(player, "hora_do_mundo", 12) or 12)

    if context.user_data.pop("mut10_penalidade_dano", False):
        dano_jogador_calculado = max(1, round(dano_jogador_calculado * 0.90))
        linhas.append("🧠 *Mente Fragmentada:* Ataque desferido com -10% de dano devido ao impacto do crítico sofrido!")

    from game.talentos import (
        verificar_lanca_purificacao,
        calcular_roubo_vida_talento,
        verificar_dot_talento_batedor,
    )
    _, ignora_def_inq = verificar_lanca_purificacao(player, monstro, session)
    defesa_alvo = 0 if ((arma_obj and arma_obj.efeito_especial == "Ignora Defesa") or ignora_def_inq) else monstro.defesa
    nv_prof_arma = 0
    if arma_obj:
        from db.models import PlayerProficiencia
        from game.proficiencia import nivel_e_progresso
        prof_obj = session.query(PlayerProficiencia).filter_by(player_id=player.id, tipo_arma=arma_obj.tipo).first()
        if prof_obj:
            nv_prof_arma, _, _ = nivel_e_progresso(prof_obj.valor or 0)

    res = resolver_ataque(
        atq_bonus_jogador, defesa_alvo, dano_jogador_calculado,
        bonus_critico_pct=calcular_critico_chance(player, nivel_proficiencia=nv_prof_arma),
    )
    nivel_novo = 0
    if res.acertou:
        from game.proficiencia import registrar_hit, bonus_dano_percentual

        dano_final = res.dano
        nivel_novo = nv_prof_arma
        if arma_obj:
            classe_obj = session.get(Classe, player.classe_id) if player.classe_id else None
            nome_classe = classe_obj.nome if classe_obj else ""
            subiu, nivel_novo = registrar_hit(session, player, arma_obj.tipo)
            player.em_combate_proficiencia_ganha = (player.em_combate_proficiencia_ganha or 0) + 1
            bonus_pct = bonus_dano_percentual(nivel_novo, nome_classe, arma_obj.tipo)
            dano_final = round(res.dano * (1 + bonus_pct))
            if subiu:
                from game.ui_utils import formatar_alerta_level_up_proficiencia
                linhas.append(formatar_alerta_level_up_proficiencia(arma_obj.tipo, nivel_novo))

        extra_emp = f" ({desc_empunhadura})" if mult_empunhadura > 1.0 else ""
        if res.critico:
            from game.ui_utils import formatar_critico_combate
            from game.proficiencia import bonus_mult_critico
            nv_arma = nivel_novo if arma_obj else 0
            mult_c = 2.0 + bonus_mult_critico(nv_arma)
            linhas.append(formatar_critico_combate(mult_c, dano_final) + extra_emp)
        else:
            from game.ui_utils import esc_md
            nome_arma_str = arma_obj.variacao if (arma_obj and arma_obj.variacao) else "seus punhos"
            linhas.append(f"Você acerta o {esc_md(monstro.nome)} com {esc_md(nome_arma_str)}! ({dano_final} de dano){extra_emp}")

        # Persistência mandatória do dano no HP do monstro
        player.em_combate_hp_monstro = max(0, player.em_combate_hp_monstro - dano_final)

        # Mecânica oficial da Adaga (25% de chance de golpe extra a 50% de dano)
        if arma_obj and "adaga" in (arma_obj.tipo or "").lower() and random.random() < 0.25:
            dano_extra = max(1, round(dano_final * 0.5))
            player.em_combate_hp_monstro = max(0, player.em_combate_hp_monstro - dano_extra)
            linhas.append(f"🗡️ Golpe rápido de Adaga! Dano extra imediato: *{dano_extra}*.")

        # Lote 3: Talentos de Nível 15 em acerto com arma
        # Conjurador de Sangue: Lâmina da Carne Corrompida (Rouba Vida 15%)
        cura_lifesteal = calcular_roubo_vida_talento(player, dano_final, session)
        if cura_lifesteal > 0:
            linhas.append(f"🩸 *Lâmina da Carne Corrompida:* Rouba Vida recuperou {cura_lifesteal} HP!")

        # Batedor dos Ecos: Nevasca Perfurante (Queimadura DoT por 2 turnos com Arco)
        dot_res = verificar_dot_talento_batedor(player, tipo_arma_str, dano_final, session)
        if dot_res["aplicou"]:
            linhas.append(dot_res["descricao"])

        # Efeitos mecânicos de armas especiais via engine unificada
        if arma_obj:
            from game.combat import rolar_efeito_arma
            texto_ef = rolar_efeito_arma(arma_obj, player, monstro, dano_final)
            if texto_ef:
                linhas.append(texto_ef)
    else:
        linhas.append("💨 Você errou o golpe.")

    if player.em_combate_hp_monstro <= 0:
        await _vitoria(session, query, player, monstro, linhas)
        return

    # --- 3) contra-ataque do monstro, com chance de aplicar efeito ---
    if player.em_combate_efeito_monstro == "Atordoado":
        linhas.append(f"💫 {monstro.nome} está atordoado e não pôde agir!")
        player.em_combate_efeito_monstro_turnos = (player.em_combate_efeito_monstro_turnos or 1) - 1
        if player.em_combate_efeito_monstro_turnos <= 0:
            player.em_combate_efeito_monstro = None
            player.em_combate_efeito_monstro_turnos = None
    else:
        res_m = resolver_ataque(monstro.atq_bonus, defesa_jogador, monstro.dano)
        if res_m.acertou:
            dano_m = res_m.dano
            if player.em_combate_efeito_jogador == "Proteção Radiante":
                dano_m = max(1, round(dano_m * 0.85))
                linhas.append("🛡️ Sua Proteção Radiante amorteceu o golpe!")
            player.hp_atual -= dano_m
            linhas.append(f"💥 {monstro.nome} acerta{' (CRÍTICO!)' if res_m.critico else ''}: *{dano_m}* de dano em você.")

            # Mutação 5: Sangue Cáustico Ácido (contra-ataque de 4 de dano)
            from game.combat import aplicar_contra_ataque_mutacao, _obter_mutacoes_player
            dano_acido = aplicar_contra_ataque_mutacao(player)
            if dano_acido > 0:
                player.em_combate_hp_monstro = max(0, player.em_combate_hp_monstro - dano_acido)
                linhas.append(f"🧪 *Sangue Cáustico:* Seu sangue ácido espirra em {monstro.nome} causando {dano_acido} de dano!")

            # Mutação 10: Mente Fragmentada (penalidade pós-crítico sofrido: -10% dano no próximo ataque)
            if res_m.critico:
                if any(getattr(m, "mutacao_id", 0) == 10 for m in _obter_mutacoes_player(player)):
                    context.user_data["mut10_penalidade_dano"] = True
                    linhas.append("🧠 *Mente Fragmentada:* O acerto crítico abalou sua concentração (-10% de dano no próximo ataque)!")

            if not player.em_combate_efeito_jogador:
                efeito_reconhecido = identificar_efeito(monstro.golpe_especial) or identificar_efeito(monstro.efeito_mecanico)
                if efeito_reconhecido and random.random() < 0.30:
                    player.em_combate_efeito_jogador = efeito_reconhecido
                    player.em_combate_efeito_jogador_turnos = turnos_padrao(efeito_reconhecido)
                    icone_ef = ICONE_EFEITO.get(efeito_reconhecido, "🔸")
                    linhas.append(f"{icone_ef} Você foi afetado por *{efeito_reconhecido}*!")
        else:
            linhas.append(f"💨 {monstro.nome} errou o ataque.")

    if player.em_combate_hp_monstro <= 0 and player.hp_atual > 0:
        await _vitoria(session, query, player, monstro, linhas)
        return

    if player.hp_atual <= 0:
        await _derrota(session, query, player, linhas, monstro)
        return

    session.commit()
    hp_monstro, hp_monstro_max = player.em_combate_hp_monstro, monstro.hp
    hp_jogador, hp_jogador_max = player.hp_atual, player.hp_max
    mana_atual, mana_max = player.mana_atual, player.mana_max
    nome_monstro, papel_monstro, nivel_monstro = monstro.nome, monstro.papel, monstro.nivel
    efeito_monstro_txt = _formata_efeito(player.em_combate_efeito_monstro, player.em_combate_efeito_monstro_turnos)
    efeito_jogador_txt = _formata_efeito(player.em_combate_efeito_jogador, player.em_combate_efeito_jogador_turnos)
    markup = _botoes_combate(session, player, monstro)
    session.close()

    await query.edit_message_text(
        f"{icone_papel} *{nome_monstro}* Nv.{nivel_monstro} ({papel_monstro}){efeito_monstro_txt}\n"
        f"❤️ {hp_monstro}/{hp_monstro_max}\n{_barra(hp_monstro, hp_monstro_max, cheio='🟥')}\n\n"
        + "\n".join(linhas) +
        f"\n\n🧍 Você{efeito_jogador_txt}\n❤️ {hp_jogador}/{hp_jogador_max}\n{_barra(hp_jogador, hp_jogador_max)}"
        + (f"\n⚡ Vigor: {player.vig_atual}/{player.vig_max}" if player.vig_max else "")
        + (f"\n🔷 Mana: {mana_atual}/{mana_max}" if mana_max else ""),
        parse_mode="Markdown",
        reply_markup=markup,
    )


async def habilidade_ativa_fisica_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Executa a habilidade ativa física inicial da classe do jogador."""
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

    icone_papel = ICONE_PAPEL.get(monstro.papel, "⚪")
    linhas = []

    # 1) Tick de efeitos ativos (DoTs e mutações)
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
        await _vitoria(session, query, player, monstro, linhas)
        return
    if player.hp_atual <= 0:
        await _derrota(session, query, player, linhas, monstro)
        return

    # 2) Execução da habilidade física ativa
    from db.models import PlayerInventario, Arma, Tier
    from game.combat import executar_habilidade_ativa, resolver_ataque
    from game.atributos import calcular_defesa_total

    arma_equipada = (
        session.query(PlayerInventario)
        .filter_by(player_id=player.id, tipo_item="arma", equipado=True)
        .first()
    )
    arma_obj = session.query(Arma).filter_by(id=arma_equipada.item_ref_id).first() if arma_equipada and arma_equipada.item_ref_id else None
    tier_jogador = session.query(Tier).filter(Tier.id == player.tier_mais_alto_alcancado).first()
    dano_arma = round(arma_obj.dano_comum * (arma_obj.mod_variacao or 1.0)) if arma_obj and arma_obj.dano_comum else (tier_jogador.dano_comum if tier_jogador else 4)
    if arma_equipada and getattr(arma_equipada, "danificado", False):
        dano_arma = round(dano_arma * 0.5)

    nome_classe = player.classe.nome if player.classe else ""
    res = executar_habilidade_ativa(
        classe_nome=nome_classe,
        jogador=player,
        alvo=monstro,
        nivel_habilidade=player.habilidade_ativa_nivel,
        session=session,
        dano_arma_equipada=dano_arma,
    )
    player.em_combate_turnos = (player.em_combate_turnos or 0) + 1

    if not res.sucesso:
        session.close()
        await query.answer(res.motivo_falha, show_alert=True)
        return

    ic_rec = "🔷" if res.recurso_tipo == "Mana" else "⚡"
    linhas.append(f"{ic_rec} Você executa *{res.habilidade_nome}*! (Gasto: {res.recurso_gasto} {res.recurso_tipo})")
    if res.acertou:
        player.em_combate_hp_monstro -= res.dano
        if arma_obj:
            from game.proficiencia import registrar_hit
            subiu, nivel_novo = registrar_hit(session, player, arma_obj.tipo)
            player.em_combate_proficiencia_ganha = (player.em_combate_proficiencia_ganha or 0) + 1
            if subiu:
                from game.ui_utils import formatar_alerta_level_up_proficiencia
                linhas.append(formatar_alerta_level_up_proficiencia(arma_obj.tipo, nivel_novo))
        linhas.append(f"⚔️ Golpe certeiro{' 💥 CRÍTICO!' if res.critico else '!'}: *{res.dano}* de dano físico.")
        if res.efeito_descricao:
            linhas.append(res.efeito_descricao)
    else:
        linhas.append(f"💨 {res.habilidade_nome} errou o alvo!")

    if player.em_combate_hp_monstro <= 0:
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
                linhas.append("🛡️ Sua Proteção Radiante amorteceu o dano recebido!")
            player.hp_atual -= dano_m
            linhas.append(f"💥 {monstro.nome} acerta{' (CRÍTICO!)' if res_m.critico else ''}: *{dano_m}* de dano em você.")

            # Mutação 5: Sangue Cáustico Ácido (contra-ataque de 4 de dano)
            from game.combat import aplicar_contra_ataque_mutacao, _obter_mutacoes_player
            dano_acido = aplicar_contra_ataque_mutacao(player)
            if dano_acido > 0:
                player.em_combate_hp_monstro = max(0, player.em_combate_hp_monstro - dano_acido)
                linhas.append(f"🧪 *Sangue Cáustico:* Seu sangue ácido espirra em {monstro.nome} causando {dano_acido} de dano!")

            # Mutação 10: Mente Fragmentada (penalidade pós-crítico sofrido: -10% dano no próximo ataque)
            if res_m.critico:
                if any(getattr(m, "mutacao_id", 0) == 10 for m in _obter_mutacoes_player(player)):
                    context.user_data["mut10_penalidade_dano"] = True
                    linhas.append("🧠 *Mente Fragmentada:* O acerto crítico abalou sua concentração (-10% de dano no próximo ataque)!")

            if not player.em_combate_efeito_jogador:
                efeito_reconhecido = identificar_efeito(monstro.golpe_especial) or identificar_efeito(monstro.efeito_mecanico)
                if efeito_reconhecido and random.random() < 0.30:
                    player.em_combate_efeito_jogador = efeito_reconhecido
                    player.em_combate_efeito_jogador_turnos = turnos_padrao(efeito_reconhecido)
                    icone_ef = ICONE_EFEITO.get(efeito_reconhecido, "🔸")
                    linhas.append(f"{icone_ef} Você foi afetado por *{efeito_reconhecido}*!")
        else:
            linhas.append(f"💨 {monstro.nome} errou o ataque.")

    if player.em_combate_hp_monstro <= 0 and player.hp_atual > 0:
        await _vitoria(session, query, player, monstro, linhas)
        return

    if player.hp_atual <= 0:
        await _derrota(session, query, player, linhas, monstro)
        return

    session.commit()
    hp_monstro, hp_monstro_max = player.em_combate_hp_monstro, monstro.hp
    hp_jogador, hp_jogador_max = player.hp_atual, player.hp_max
    mana_atual, mana_max = player.mana_atual, player.mana_max
    nome_monstro, papel_monstro, nivel_monstro = monstro.nome, monstro.papel, monstro.nivel
    efeito_monstro_txt = _formata_efeito(player.em_combate_efeito_monstro, player.em_combate_efeito_monstro_turnos)
    efeito_jogador_txt = _formata_efeito(player.em_combate_efeito_jogador, player.em_combate_efeito_jogador_turnos)
    markup = _botoes_combate(session, player, monstro)
    session.close()

    await query.edit_message_text(
        f"{icone_papel} *{nome_monstro}* Nv.{nivel_monstro} ({papel_monstro}){efeito_monstro_txt}\n"
        f"❤️ {hp_monstro}/{hp_monstro_max}\n{_barra(hp_monstro, hp_monstro_max, cheio='🟥')}\n\n"
        + "\n".join(linhas) +
        f"\n\n🧍 Você{efeito_jogador_txt}\n❤️ {hp_jogador}/{hp_jogador_max}\n{_barra(hp_jogador, hp_jogador_max)}"
        + (f"\n⚡ Vigor: {player.vig_atual}/{player.vig_max}" if player.vig_max else "")
        + (f"\n🔷 Mana: {mana_atual}/{mana_max}" if mana_max else ""),
        parse_mode="Markdown",
        reply_markup=markup,
    )


def _formata_efeito(nome, turnos):
    if not nome or not turnos:
        return ""
    icone = ICONE_EFEITO.get(nome, "🔸")
    return f"  [{icone} {turnos}t]"


async def _vitoria(session, query, player, monstro, linhas):
    import json
    from db.models import CurvaMestra
    from game.loot import resolver_loot

    curva = session.query(CurvaMestra).filter_by(nivel=player.nivel).first()
    bonus_drop = 0.0
    try:
        from game.proficiencia import bonus_drop_materiais_pct, nivel_e_progresso
        from db.models import PlayerInventario, Arma, PlayerProficiencia
        arma_eq = session.query(PlayerInventario).filter_by(player_id=player.id, equipado=True, tipo_item="arma").first()
        if arma_eq and arma_eq.item_ref_id:
            arma_ref = session.query(Arma).filter_by(id=arma_eq.item_ref_id).first()
            if arma_ref and arma_ref.tipo:
                pp = session.query(PlayerProficiencia).filter_by(player_id=player.id, tipo_arma=arma_ref.tipo).first()
                if pp:
                    nv_prof, _, _ = nivel_e_progresso(pp.valor)
                    bonus_drop = bonus_drop_materiais_pct(nv_prof)
    except Exception:
        pass
    xp_ganho, ouro_ganho, materiais = resolver_loot(session, player, monstro, curva, bonus_drop_pct=bonus_drop)
    from game.loot import sortear_equipamento_loot
    equipamento_dropado = sortear_equipamento_loot(session, monstro)

    from game.codex import registrar_vitoria
    registrar_vitoria(session, player, monstro.id)

    if monstro.papel in ("Boss", "Cosmico"):
        from game.economia import _normalizar
        derrotados = (player.bosses_derrotados or "").split("|") if player.bosses_derrotados else []
        if not any(_normalizar(d) == _normalizar(monstro.nome) for d in derrotados):
            derrotados.append(monstro.nome)
        player.bosses_derrotados = "|".join(filter(None, derrotados))

    from game.missoes import registrar_abate
    avancos_missao = registrar_abate(session, player, monstro.nome, monstro.id, player.local_atual)

    player.xp_atual += xp_ganho
    player.ouro += ouro_ganho
    player.combates_vencidos_qtd = (player.combates_vencidos_qtd or 0) + 1
    try:
        from game.titulos import verificar_titulos_contadores
        verificar_titulos_contadores(session, player)
    except Exception:
        pass
    curou_medo = False
    if player.debuff_ativo == "Marca do Medo":
        player.debuff_ativo = None
        curou_medo = True

    from game.nivel import verificar_e_aplicar_level_up
    niveis_subidos = verificar_e_aplicar_level_up(session, player)
    player.em_combate_monstro_id = None
    player.em_combate_hp_monstro = None
    player.em_combate_efeito_monstro = None
    player.em_combate_efeito_monstro_turnos = None
    player.em_combate_efeito_jogador = None
    player.em_combate_efeito_jogador_turnos = None
    loot_completo = {"materiais": materiais, "equipamento": equipamento_dropado}
    player.loot_pendente = json.dumps(loot_completo, ensure_ascii=False)

    session.commit()
    nome_derrotado, ouro_total, xp_total = monstro.nome, player.ouro, player.xp_atual
    turnos_luta = player.em_combate_turnos or 0
    prof_ganha = player.em_combate_proficiencia_ganha or 0
    from db.models import PlayerInventario
    arma_equipada = (
        session.query(PlayerInventario)
        .filter_by(player_id=player.id, tipo_item="arma", equipado=True)
        .first()
    )
    nome_arma_equipada = arma_equipada.nome_item if arma_equipada else None
    session.close()

    total_itens_loot = len(materiais) + (1 if equipamento_dropado else 0)
    botoes = [[InlineKeyboardButton(
        f"🎁 Lootear{' (' + str(total_itens_loot) + ')' if total_itens_loot else ' (nada)'}",
        callback_data="lootear",
    )], [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]

    resumo = (
        "\n".join(linhas) +
        f"\n\n🏆 *Você derrotou {nome_derrotado}!*\n\n"
        f"⏱️ Duração: {turnos_luta} turno{'s' if turnos_luta != 1 else ''}\n"
        f"✨ +{xp_ganho} XP (total: {xp_total})\n"
        f"💰 +{ouro_ganho} Ouro (total: {ouro_total})"
    )
    if prof_ganha and nome_arma_equipada:
        resumo += f"\n🗡️ +{prof_ganha} Proficiência com {nome_arma_equipada}"
    if curou_medo:
        resumo += "\n✨ *A vitória dissipou seu pavor! O debuff 'Marca do Medo' foi curado.*"
    if niveis_subidos:
        resumo += f"\n\n🎉 *LEVEL UP! Você chegou ao Nível {niveis_subidos[-1]}!*"
    if avancos_missao:
        resumo += "\n\n" + "\n".join(avancos_missao)

    await query.edit_message_text(
        resumo,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(botoes),
    )


async def _derrota(session, query, player, linhas, monstro):
    from game.combat import resolver_derrota
    from game.mapa import cidade_polo_do_local
    from game.corrupcao import aplicar_ganho_corrupcao

    local_atual = session.query(Local).filter_by(nome=player.local_atual).first()
    tipo_local_atual = local_atual.tipo if local_atual else None
    cidade = cidade_polo_do_local(session, player.local_atual)
    nome_cidade_destino = cidade.nome if cidade else (player.local_atual or "Vila Inicial")

    corr_anterior = player.corrupcao or 0

    resultado = resolver_derrota(
        player.ouro, corr_anterior, player.hora_do_mundo,
        monstro.papel if monstro else "Comum", tipo_local_atual,
        player=player,
    )

    pontos_corr, nova_corrupcao, subiu_estagio = aplicar_ganho_corrupcao(
        session, player, monstro.papel if monstro else "Comum"
    )

    nome_monstro = monstro.nome if monstro else "algo nas sombras"

    novo_debuff = resultado.get("debuff_sorteado")
    if novo_debuff:
        player.debuff_ativo = novo_debuff

    player.hp_atual = 1
    player.vig_atual = 0
    player.ouro = resultado["ouro_novo"]
    player.corrupcao = nova_corrupcao
    player.hora_do_mundo = resultado["hora_nova"]
    player.local_atual = nome_cidade_destino
    player.em_combate_monstro_id = None
    player.em_combate_hp_monstro = None
    player.em_combate_efeito_monstro = None
    player.em_combate_efeito_monstro_turnos = None
    player.em_combate_efeito_jogador = None
    player.em_combate_efeito_jogador_turnos = None
    session.commit()
    session.close()

    from game.ui_utils import formatar_resumo_derrota
    resumo_oficial = formatar_resumo_derrota(
        nome_monstro=nome_monstro,
        ouro_perdido=resultado["ouro_perdido"],
        pontos_corr=pontos_corr,
        corr_anterior=corr_anterior,
        nova_corrupcao=nova_corrupcao,
        subiu_estagio=subiu_estagio,
        debuff_sorteado=player.debuff_ativo,
    )

    texto = (
        ("\n".join(linhas) + "\n\n" if linhas else "")
        + resumo_oficial + "\n\n"
        f"📍 *Despertou em:* {nome_cidade_destino}\n"
        f"⏳ *Tempo decorrido:* +4 horas\n\n"
        f"_{resultado['frase_narrativa']}_"
    )
    await query.edit_message_text(
        texto, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🛏️ Descansar na Estalagem", callback_data="descansar")],
             [InlineKeyboardButton("🏛️ Ir para o Centro da Cidade", callback_data="menu_status")]]
        ),
    )


async def voltar_combate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Botao 'Voltar ao combate' do menu de Magias - so redesenha a tela atual."""
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    monstro = session.get(Monstro, player.em_combate_monstro_id) if player.em_combate_monstro_id else None
    if monstro is None:
        session.close()
        await query.edit_message_text(
            "Esse combate não está mais ativo.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]),
        )
        return
    icone_papel = ICONE_PAPEL.get(monstro.papel, "⚪")
    hp_m, hp_m_max = player.em_combate_hp_monstro, monstro.hp
    hp_j, hp_j_max = player.hp_atual, player.hp_max
    mana_atual, mana_max = player.mana_atual, player.mana_max
    markup = _botoes_combate(session, player, monstro)
    nome_monstro = monstro.nome
    nivel_monstro = monstro.nivel
    papel_monstro = monstro.papel
    session.close()
    await query.edit_message_text(
        f"{icone_papel} *{nome_monstro}* Nv.{nivel_monstro} ({papel_monstro})\n"
        f"❤️ {hp_m}/{hp_m_max}\n{_barra(hp_m, hp_m_max, cheio='🟥')}\n\n"
        f"🧍 Você\n❤️ {hp_j}/{hp_j_max}\n{_barra(hp_j, hp_j_max)}"
        + (f"\n⚡ Vigor: {player.vig_atual}/{player.vig_max}" if player.vig_max else "")
        + (f"\n🔷 Mana: {mana_atual}/{mana_max}" if mana_max else ""),
        parse_mode="Markdown",
        reply_markup=markup,
    )


async def fugir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    if chance_fuga(player=player):
        player.em_combate_monstro_id = None
        player.em_combate_hp_monstro = None
        player.em_combate_efeito_monstro = None
        player.em_combate_efeito_monstro_turnos = None
        player.em_combate_efeito_jogador = None
        player.em_combate_efeito_jogador_turnos = None
        try:
            from game.titulos import verificar_titulos_contadores
            verificar_titulos_contadores(session, player)
        except Exception:
            pass
        session.commit()
        session.close()
        await query.edit_message_text(
            "🏃 *Você fugiu com sucesso.*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return

    monstro = session.get(Monstro, player.em_combate_monstro_id) if player.em_combate_monstro_id else None
    if monstro is None:
        session.close()
        await query.edit_message_text(
            "Esse combate não está mais ativo.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return

    from game.atributos import calcular_defesa_total
    defesa_jogador = calcular_defesa_total(player, session)
    res_m = resolver_ataque(monstro.atq_bonus, defesa_jogador, monstro.dano)
    texto = "🏃 *Fuga falhou!*"
    linhas = [texto]
    if res_m.acertou:
        player.hp_atual -= res_m.dano
        texto += f"\n{monstro.nome} acerta um golpe livre: *{res_m.dano}* de dano."
        linhas.append(f"{monstro.nome} acerta um golpe livre: *{res_m.dano}* de dano.")

    if player.hp_atual <= 0:
        await _derrota(session, query, player, linhas, monstro)
        return
    session.commit()
    hp_jogador = player.hp_atual
    hp_jogador_max = player.hp_max
    markup = _botoes_combate(session, player, monstro)
    session.close()
    await query.edit_message_text(
        texto + f"\n\n❤️ Você: {hp_jogador}/{hp_jogador_max}\n{_barra(hp_jogador, hp_jogador_max)}"
        + (f"\n⚡ Vigor: {player.vig_atual}/{player.vig_max}" if player.vig_max else "")
        + (f"\n🔷 Mana: {player.mana_atual}/{player.mana_max}" if player.mana_max else ""),
        parse_mode="Markdown",
        reply_markup=markup,
    )


async def lootear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import json
    from game.loot import aplicar_loot_no_inventario

    query = update.callback_query
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    dados_brutos = json.loads(player.loot_pendente) if player.loot_pendente else None
    if not dados_brutos:
        await query.answer("Não há nada pra lootear.", show_alert=True)
        session.close()
        return

    await query.answer()

    if isinstance(dados_brutos, dict):
        materiais = dados_brutos.get("materiais", [])
        equipamento = dados_brutos.get("equipamento")
    else:
        # retrocompatibilidade caso seja lista legada
        materiais = dados_brutos
        equipamento = None

    if materiais:
        aplicar_loot_no_inventario(session, player, materiais)

    linhas_loot_itens = []
    if materiais:
        linhas_loot_itens.extend(f"📦 +{qtd}x {nome}" for nome, qtd in materiais)

    if equipamento:
        from db.models import PlayerInventario
        item_eq = PlayerInventario(
            player_id=player.id,
            tipo_item=equipamento["tipo_item"],
            item_ref_id=equipamento["item_ref_id"],
            nome_item=equipamento["nome_item"],
            danificado=True,
            quantidade=1,
            equipado=False,
        )
        session.add(item_eq)
        linhas_loot_itens.append(f"⚔️ +1x {equipamento['nome_item']}")

    player.loot_pendente = None

    from game.missoes import registrar_coleta
    avancos_coleta = []
    if materiais:
        for nome_mat, qtd_mat in materiais:
            avancos_coleta.extend(registrar_coleta(session, player, nome_mat, qtd_mat, player.local_atual))

    session.commit()

    linhas_loot = "\n".join(linhas_loot_itens) if linhas_loot_itens else "Nenhum item coletado."
    if avancos_coleta:
        linhas_loot += "\n\n" + "\n".join(avancos_coleta)
    session.close()

    await query.edit_message_text(
        f"🎁 *Você lootou:*\n\n{linhas_loot}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
        ),
    )


async def poupar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    monstro = session.query(Monstro).filter_by(id=player.em_combate_monstro_id).first()

    if not monstro or not verificar_pode_poupar(
        monstro, player.em_combate_hp_monstro or monstro.hp, monstro.hp
    ):
        await query.answer("Não é possível poupar agora.", show_alert=True)
        session.close()
        return

    await query.answer()

    nome_poupado = monstro.nome
    nome_curto_poupado = nome_poupado.split(",")[0].strip()
    gancho = monstro.interacao_ambiental or ""

    from game.titulos import verificar_titulo_por_poupar
    titulos_ganhos = verificar_titulo_por_poupar(session, player, nome_poupado)

    existentes = (player.monstros_poupados or "").split("|") if player.monstros_poupados else []
    if nome_curto_poupado not in existentes:
        existentes.append(nome_curto_poupado)
    player.monstros_poupados = "|".join(filter(None, existentes))

    player.em_combate_monstro_id = None
    player.em_combate_hp_monstro = None
    player.em_combate_efeito_monstro = None
    player.em_combate_efeito_monstro_turnos = None
    player.em_combate_efeito_jogador = None
    player.em_combate_efeito_jogador_turnos = None
    session.commit()
    session.close()

    texto = f"🕊️ *Você poupou {nome_poupado}.*\n\n_{gancho}_"
    if titulos_ganhos:
        for t in titulos_ganhos:
            texto += f"\n\n🏆 *Título conquistado: {t.nome}*"

    await query.edit_message_text(
        texto,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
        ),
    )
