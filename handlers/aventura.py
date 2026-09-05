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
    await menu_aventura(update, context)


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
            "_(Descanso ainda não foi implementado — chega numa fase futura.)_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
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
    texto = (
        f"⚔️ *COMBATE INICIADO*\n"
        f"{icone_local} {local.nome}\n\n"
        f"{icone_papel} *{monstro.nome}* — Nv.{monstro.nivel} ({monstro.papel})\n"
        f"❤️ {monstro.hp}/{monstro.hp}\n{_barra(monstro.hp, monstro.hp, cheio='🟥')}\n\n"
    )
    if monstro.motivacao:
        texto += f"_{monstro.motivacao}_\n\n"
    texto += (
        f"🗡️ Golpe: {monstro.golpe_especial}\n\n"
        f"⚡ Seu Vigor: {vig_atual}/{vig_max}"
        + (f"\n🔷 Mana: {mana_atual}/{mana_max}" if mana_max else "")
    )
    session.close()
    botoes = [[InlineKeyboardButton("⚔️ Atacar", callback_data="atacar")]]
    if verificar_pode_poupar(monstro, monstro.hp, monstro.hp):
        botoes.append([InlineKeyboardButton("🕊️ Poupar", callback_data="poupar")])
    if mana_max:
        botoes[0].append(InlineKeyboardButton("✨ Magias", callback_data="menu_magias"))
    botoes.append([InlineKeyboardButton("🏃 Fugir", callback_data="fugir")])
    await query.edit_message_text(
        texto, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(botoes),
    )


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
    defesa_jogador = curva.defesa_esperada if curva else 6
    icone_papel = ICONE_PAPEL.get(monstro.papel, "⚪")

    linhas = []

    # --- 1) tick dos efeitos ativos (dano periodico de Sangramento/Queimadura/Veneno) ---
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
        await _derrota(session, query, player, linhas)
        return

    # --- 2) ataque do jogador ---
    from game.atributos import bonus_dano_por_for, bonus_critico_por_des
    dano_jogador_base += bonus_dano_por_for(player.atributo_for or 10)
    res = resolver_ataque(
        atq_bonus_jogador, monstro.defesa, dano_jogador_base,
        bonus_critico_pct=bonus_critico_por_des(player.atributo_des or 10),
    )
    if res.acertou:
        from db.models import PlayerInventario, Classe
        from game.proficiencia import registrar_hit, nivel_e_progresso, bonus_dano_percentual

        arma_equipada = (
            session.query(PlayerInventario)
            .filter_by(player_id=player.id, tipo_item="arma", equipado=True)
            .first()
        )
        dano_final = res.dano
        if arma_equipada and arma_equipada.item_ref_id:
            from db.models import Arma
            arma_obj = session.query(Arma).filter_by(id=arma_equipada.item_ref_id).first()
            if arma_obj:
                classe_obj = session.get(Classe, player.classe_id) if player.classe_id else None
                nome_classe = classe_obj.nome if classe_obj else ""
                subiu, nivel_novo = registrar_hit(session, player, arma_obj.tipo)
                player.em_combate_proficiencia_ganha = (player.em_combate_proficiencia_ganha or 0) + 1
                bonus_pct = bonus_dano_percentual(nivel_novo, nome_classe, arma_obj.tipo)
                dano_final = round(res.dano * (1 + bonus_pct))
                if subiu:
                    linhas.append(f"📈 Proficiência com {arma_obj.tipo} subiu pro Nv.{nivel_novo}!")

        player.em_combate_hp_monstro -= dano_final
        linhas.append(f"⚔️ Você acerta{' 💥 CRÍTICO!' if res.critico else ''}: *{dano_final}* de dano.")
    else:
        linhas.append("💨 Você errou o golpe.")

    if player.em_combate_hp_monstro <= 0:
        await _vitoria(session, query, player, monstro, linhas)
        return

    # --- 3) contra-ataque do monstro, com chance de aplicar efeito ---
    res_m = resolver_ataque(monstro.atq_bonus, defesa_jogador, monstro.dano)
    if res_m.acertou:
        player.hp_atual -= res_m.dano
        linhas.append(f"💥 {monstro.nome} acerta{' (CRÍTICO!)' if res_m.critico else ''}: *{res_m.dano}* de dano em você.")

        if not player.em_combate_efeito_jogador:
            efeito_reconhecido = identificar_efeito(monstro.golpe_especial) or identificar_efeito(monstro.efeito_mecanico)
            if efeito_reconhecido and random.random() < 0.30:
                player.em_combate_efeito_jogador = efeito_reconhecido
                player.em_combate_efeito_jogador_turnos = turnos_padrao(efeito_reconhecido)
                icone_ef = ICONE_EFEITO.get(efeito_reconhecido, "🔸")
                linhas.append(f"{icone_ef} Você foi afetado por *{efeito_reconhecido}*!")
    else:
        linhas.append(f"💨 {monstro.nome} errou o ataque.")

    if player.hp_atual <= 0:
        await _derrota(session, query, player, linhas)
        return

    session.commit()
    hp_monstro, hp_monstro_max = player.em_combate_hp_monstro, monstro.hp
    hp_jogador, hp_jogador_max = player.hp_atual, player.hp_max
    mana_atual, mana_max = player.mana_atual, player.mana_max
    nome_monstro, papel_monstro, nivel_monstro = monstro.nome, monstro.papel, monstro.nivel
    efeito_monstro_txt = _formata_efeito(player.em_combate_efeito_monstro, player.em_combate_efeito_monstro_turnos)
    efeito_jogador_txt = _formata_efeito(player.em_combate_efeito_jogador, player.em_combate_efeito_jogador_turnos)
    session.close()

    botoes = [[InlineKeyboardButton("⚔️ Atacar", callback_data="atacar")]]
    if verificar_pode_poupar(monstro, hp_monstro, hp_monstro_max):
        botoes.append([InlineKeyboardButton("🕊️ Poupar", callback_data="poupar")])
    if mana_max:
        botoes[0].append(InlineKeyboardButton("✨ Magias", callback_data="menu_magias"))
    botoes.append([InlineKeyboardButton("🏃 Fugir", callback_data="fugir")])

    await query.edit_message_text(
        f"{icone_papel} *{nome_monstro}* Nv.{nivel_monstro} ({papel_monstro}){efeito_monstro_txt}\n"
        f"❤️ {hp_monstro}/{hp_monstro_max}\n{_barra(hp_monstro, hp_monstro_max, cheio='🟥')}\n\n"
        + "\n".join(linhas) +
        f"\n\n🧍 Você{efeito_jogador_txt}\n❤️ {hp_jogador}/{hp_jogador_max}\n{_barra(hp_jogador, hp_jogador_max)}"
        + (f"\n🔷 Mana: {mana_atual}/{mana_max}" if mana_max else ""),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(botoes),
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
    xp_ganho, ouro_ganho, materiais = resolver_loot(session, player, monstro, curva)

    from game.codex import registrar_vitoria
    registrar_vitoria(session, player, monstro.id)

    player.xp_atual += xp_ganho
    player.ouro += ouro_ganho
    from game.nivel import verificar_e_aplicar_level_up
    niveis_subidos = verificar_e_aplicar_level_up(session, player)
    player.em_combate_monstro_id = None
    player.em_combate_hp_monstro = None
    player.em_combate_efeito_monstro = None
    player.em_combate_efeito_monstro_turnos = None
    player.em_combate_efeito_jogador = None
    player.em_combate_efeito_jogador_turnos = None
    player.loot_pendente = json.dumps(materiais, ensure_ascii=False)

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

    botoes = [[InlineKeyboardButton(
        f"🎁 Lootear{' (' + str(len(materiais)) + ')' if materiais else ' (nada)'}",
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
    if niveis_subidos:
        resumo += f"\n\n🎉 *LEVEL UP! Você chegou ao Nível {niveis_subidos[-1]}!*"

    await query.edit_message_text(
        resumo,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(botoes),
    )


async def _derrota(session, query, player, linhas):
    player.hp_atual = 1
    player.em_combate_monstro_id = None
    player.em_combate_hp_monstro = None
    player.em_combate_efeito_monstro = None
    player.em_combate_efeito_monstro_turnos = None
    player.em_combate_efeito_jogador = None
    player.em_combate_efeito_jogador_turnos = None
    session.commit()
    session.close()
    await query.edit_message_text(
        "\n".join(linhas) + "\n\n☠️ *Você quase morreu* e recua do combate, ferido.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
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
    nome_monstro, papel_monstro, nivel_monstro = monstro.nome, monstro.papel, monstro.nivel
    session.close()
    botoes = [[InlineKeyboardButton("⚔️ Atacar", callback_data="atacar")]]
    if verificar_pode_poupar(monstro, hp_m, hp_m_max):
        botoes.append([InlineKeyboardButton("🕊️ Poupar", callback_data="poupar")])
    if mana_max:
        botoes[0].append(InlineKeyboardButton("✨ Magias", callback_data="menu_magias"))
    botoes.append([InlineKeyboardButton("🏃 Fugir", callback_data="fugir")])
    await query.edit_message_text(
        f"{icone_papel} *{nome_monstro}* Nv.{nivel_monstro} ({papel_monstro})\n"
        f"❤️ {hp_m}/{hp_m_max}\n{_barra(hp_m, hp_m_max, cheio='🟥')}\n\n"
        f"🧍 Você\n❤️ {hp_j}/{hp_j_max}\n{_barra(hp_j, hp_j_max)}"
        + (f"\n🔷 Mana: {mana_atual}/{mana_max}" if mana_max else ""),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(botoes),
    )


async def fugir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    if chance_fuga():
        player.em_combate_monstro_id = None
        player.em_combate_hp_monstro = None
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

    curva = _curva(session, player.nivel)
    defesa_jogador = curva.defesa_esperada if curva else 6
    res_m = resolver_ataque(monstro.atq_bonus, defesa_jogador, monstro.dano)
    texto = "🏃 *Fuga falhou!*"
    if res_m.acertou:
        player.hp_atual -= res_m.dano
        texto += f"\n{monstro.nome} acerta um golpe livre: *{res_m.dano}* de dano."
    session.commit()
    hp_jogador, hp_jogador_max = player.hp_atual, player.hp_max
    session.close()
    await query.edit_message_text(
        texto + f"\n\n❤️ Você: {hp_jogador}/{hp_jogador_max}\n{_barra(hp_jogador, hp_jogador_max)}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⚔️ Atacar", callback_data="atacar"),
              InlineKeyboardButton("🏃 Fugir", callback_data="fugir")]]
        ),
    )


async def lootear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import json
    from game.loot import aplicar_loot_no_inventario

    query = update.callback_query
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    materiais = json.loads(player.loot_pendente) if player.loot_pendente else []
    if not materiais:
        await query.answer("Não há nada pra lootear.", show_alert=True)
        session.close()
        return

    await query.answer()

    aplicar_loot_no_inventario(session, player, materiais)
    player.loot_pendente = None
    session.commit()

    linhas_loot = "\n".join(f"📦 +{qtd}x {nome}" for nome, qtd in materiais)
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
