"""
Fase 6 — Mapa: navegacao em duas camadas (Regional + Global), aprovado no laudo 1.
Regional = locais do Polo atual do jogador. Global = mapa-mundi dos 7 Polos/Cidades.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.connection import get_session
from db.models import Player, Local, Cidade
from game.mapa import (
    monstro_do_covil, cidade_polo_do_local,
    locais_do_polo, covil_esta_descoberto, boss_e_local_do_portao,
    portao_liberado, cidades_desbloqueadas, _boss_foi_derrotado,
    local_da_cidade, local_esta_desbloqueado,
)
from game.combat import verificar_pode_poupar

ICONE_TIPO_LOCAL = {
    "Cidade": "🏰", "Estrada Perigosa": "🛤️", "Mina": "⛏️", "Dungeon": "🕸️",
    "Ruina": "🏛️", "Floresta Perigosa": "🌲", "Caverna": "🕳️",
    "Planicie Selvagem": "🌾", "Fenda": "🌋", "Campo de Batalha": "⚔️",
    "Pantano": "🐊", "Covil de Boss": "💀", "Ritual": "🔮", "Portal": "🌀",
    "Local Secreto": "❓",
}
BARRA_PERIGO = {1: "🟢", 2: "🟢", 3: "🟡", 4: "🟠", 5: "🔴"}
ROMANOS = ["I", "II", "III", "IV", "V", "VI", "VII"]

from game.ui_utils import barra as _barra_hp


def _nome_curto_cidade(cidade):
    if cidade.nome_oficial:
        return cidade.nome_oficial.split(" (")[0].strip()
    return cidade.nome


def _linha_local(local, marca="", rotulo_extra=""):
    icone = ICONE_TIPO_LOCAL.get(local.tipo, "📍")
    barra = BARRA_PERIGO.get(local.perigo, "🟡") * (local.perigo or 1)
    nivel_txt = f"Nv. {local.nivel_ref}" if local.nivel_ref else "Nv. ?"
    return f"{icone} {marca}{local.nome}{rotulo_extra}\n↳ {nivel_txt}  |  Ameaça: {barra}\n"


async def menu_mapa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _desenhar_regional(query, update)


async def mapa_regional(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _desenhar_regional(query, update)


async def _desenhar_regional(query, update):
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    cidade = cidade_polo_do_local(session, player.local_atual)
    if cidade is None:
        session.close()
        await query.edit_message_text(
            "🗺️ Não consegui identificar em qual região do mapa você está agora.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]),
        )
        return

    locais = locais_do_polo(session, cidade)
    local_cidade = local_da_cidade(session, cidade)
    normais = [l for l in locais if l.tipo not in ("Covil de Boss", "Cidade")
               and local_esta_desbloqueado(l, player)]
    covis = [l for l in locais if l.tipo == "Covil de Boss"]
    covis_descobertos = [c for c in covis if covil_esta_descoberto(c, player, locais)]

    texto = (
        f"🗺️ *Mapa Regional — Polo de {_nome_curto_cidade(cidade)}*\n"
        f"📍 Local Atual: {player.local_atual}\n"
        f"══════════════════════\n\n"
    )
    botoes = []

    if local_cidade:
        marca = "📍 " if local_cidade.nome == player.local_atual else ""
        texto += _linha_local(local_cidade, marca, " [Cidade]") + "\n"
        if local_cidade.nome != player.local_atual:
            botoes.append([InlineKeyboardButton(f"Viajar: {local_cidade.nome}", callback_data=f"mapa_ir_{local_cidade.id}")])

    for local in normais:
        marca = "📍 " if local.nome == player.local_atual else ""
        texto += _linha_local(local, marca) + "\n"
        if local.nome != player.local_atual:
            botoes.append([InlineKeyboardButton(f"Viajar: {local.nome}", callback_data=f"mapa_ir_{local.id}")])

    if covis_descobertos:
        texto += "──────────────────────\n⚔️ COVIS DESCOBERTOS\n──────────────────────\n"
        for covil in covis_descobertos:
            marca = "📍 " if covil.nome == player.local_atual else ""
            texto += _linha_local(covil, marca) + "\n"
            if covil.nome != player.local_atual:
                botoes.append([InlineKeyboardButton(f"⚔️ {covil.nome}", callback_data=f"mapa_ir_{covil.id}")])

    liberado, proxima = portao_liberado(session, player, cidade)
    if proxima:
        boss, _covil_portao = boss_e_local_do_portao(session, cidade)
        polo_num = proxima.id  # ids sao sequenciais 1..7, na mesma ordem dos Polos
        romano = ROMANOS[polo_num - 1] if 1 <= polo_num <= len(ROMANOS) else str(polo_num)
        local_proxima = local_da_cidade(session, proxima)
        nivel_txt = f"Nv. {local_proxima.nivel_ref}" if local_proxima and local_proxima.nivel_ref else "Nv. ?"
        req_boss = f"Derrotar {boss.nome} (Nv. {boss.nivel})" if boss else "—"
        cadeado = "🔓" if liberado else "🔒"
        texto += (
            "──────────────────────\n🚪 PORTÃO REGIONAL\n──────────────────────\n"
            f"{cadeado} {proxima.nome} (Polo {romano})\n"
            f"↳ {nivel_txt}  |  Req. {req_boss}\n"
        )
        botoes.append([InlineKeyboardButton(
            f"{'🚪' if liberado else '🔒'} Ir para {proxima.nome}", callback_data="mapa_portao",
        )])

    botoes.append([InlineKeyboardButton("🌍 Mapa-Múndi", callback_data="mapa_global")])
    botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")])
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def mapa_global(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    cidade_atual = cidade_polo_do_local(session, player.local_atual)

    lista = cidades_desbloqueadas(session, player)
    polo_atual_num = cidade_atual.id if cidade_atual else 1
    romano_atual = ROMANOS[polo_atual_num - 1] if 1 <= polo_atual_num <= len(ROMANOS) else str(polo_atual_num)

    texto = (
        f"🗺️ *Mapa-Múndi — Continente de Zeyrith*\n"
        f"📍 Local Atual: {player.local_atual} (Polo {romano_atual})\n"
        f"══════════════════════\n\n"
    )
    botoes = []
    bloqueadas_txt = ""
    for cidade, desbloqueada in lista:
        tiers = cidade.tiers_cobertos or ""
        atual = cidade_atual and cidade.id == cidade_atual.id
        if atual:
            texto += f"🏰 {cidade.nome} [Atual]\n↳ Nv. {cidade.nivel_min}-{cidade.nivel_max}  |  Tiers: {tiers}\n\n"
        elif desbloqueada:
            texto += f"🏰 {cidade.nome}\n↳ Nv. {cidade.nivel_min}-{cidade.nivel_max}  |  Tiers: {tiers}\n\n"
            botoes.append([InlineKeyboardButton(f"✈️ Viajar: {cidade.nome}", callback_data=f"mapa_ir_cidade_{cidade.id}")])
        else:
            bloqueadas_txt += f"🔒 {cidade.nome}\n↳ Nv. {cidade.nivel_min}-{cidade.nivel_max}  |  Tiers: {tiers}\n\n"

    if bloqueadas_txt:
        texto += "──────────────────────\n🔒 POLOS BLOQUEADOS\n──────────────────────\n" + bloqueadas_txt

    botoes.append([InlineKeyboardButton("🗺️ Mapa Regional", callback_data="mapa_regional")])
    botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")])
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def mapa_ir_cidade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cidade_id = int(query.data.split("_")[-1])
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    cidade_destino = session.query(Cidade).filter_by(id=cidade_id).first()
    if not cidade_destino:
        await query.answer("Cidade não encontrada.", show_alert=True)
        session.close()
        return

    lista = cidades_desbloqueadas(session, player)
    desbloqueada = any(c.id == cidade_destino.id and ok for c, ok in lista)
    if not desbloqueada:
        await query.answer("🔒 Esse Polo ainda não está liberado.", show_alert=True)
        session.close()
        return

    await query.answer(f"✈️ Você viajou para {cidade_destino.nome}.")
    player.local_atual = cidade_destino.nome
    visitados = (player.locais_visitados or "").split("|") if player.locais_visitados else []
    if cidade_destino.nome not in visitados:
        visitados.append(cidade_destino.nome)
    player.locais_visitados = "|".join(filter(None, visitados))
    session.commit()
    await _desenhar_regional(query, update)


async def mapa_atravessar_portao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    cidade_atual = cidade_polo_do_local(session, player.local_atual)
    if not cidade_atual:
        await query.answer("Não identifiquei sua região atual.", show_alert=True)
        session.close()
        return

    liberado, proxima = portao_liberado(session, player, cidade_atual)
    if not proxima:
        await query.answer("Você já está no Polo mais avançado do mapa.", show_alert=True)
        session.close()
        return
    if not liberado:
        boss, _ = boss_e_local_do_portao(session, cidade_atual)
        falta = []
        local_proxima = local_da_cidade(session, proxima)
        if local_proxima and (player.nivel or 1) < (local_proxima.nivel_ref or 1):
            falta.append(f"Nível {local_proxima.nivel_ref}+")
        if boss and not _boss_foi_derrotado(player, boss):
            falta.append(f"derrotar {boss.nome}")
        await query.answer("🔒 Ainda falta: " + " e ".join(falta), show_alert=True)
        session.close()
        return

    await query.answer(f"🚪 Você atravessou o Portão Regional e chegou em {proxima.nome}!")
    player.local_atual = proxima.nome
    visitados = (player.locais_visitados or "").split("|") if player.locais_visitados else []
    if proxima.nome not in visitados:
        visitados.append(proxima.nome)
    player.locais_visitados = "|".join(filter(None, visitados))
    session.commit()
    await _desenhar_regional(query, update)


async def viajar_local(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    local_id = int(query.data.split("_")[-1])
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    local = session.query(Local).filter_by(id=local_id).first()

    if not local:
        await query.answer("Local não encontrado.", show_alert=True)
        session.close()
        return

    await query.answer()

    player.local_atual = local.nome
    visitados = (player.locais_visitados or "").split("|") if player.locais_visitados else []
    if local.nome not in visitados:
        visitados.append(local.nome)
    player.locais_visitados = "|".join(filter(None, visitados))
    session.commit()

    if local.tipo == "Covil de Boss":
        await _entrar_covil(session, query, player, local)
        return

    icone = ICONE_TIPO_LOCAL.get(local.tipo, "📍")
    descricao, tipo, nome_local, cidade = local.descricao, local.tipo, local.nome, local.cidade_proxima
    subtitulo = tipo if (not cidade or cidade == nome_local) else f"{tipo} · perto de {cidade}"
    session.close()
    await query.edit_message_text(
        f"{icone} *Você chegou em {nome_local}*\n_{subtitulo}_\n\n{descricao}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔍 Ir pra Aventura", callback_data="menu_aventura")],
             [InlineKeyboardButton("🗺️ Voltar ao Mapa", callback_data="mapa_regional")]]
        ),
    )


async def _entrar_covil(session, query, player, local):
    """Covil de Boss pula o sorteio aleatorio -- vai direto pro Boss exclusivo."""
    monstro = monstro_do_covil(session, local)
    if not monstro:
        nome_local = local.nome
        session.close()
        await query.edit_message_text(
            f"💀 *{nome_local}*\n\nEstá vazio por enquanto — nenhum Boss configurado aqui ainda.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🗺️ Voltar ao Mapa", callback_data="mapa_regional")]]
            ),
        )
        return

    player.em_combate_monstro_id = monstro.id
    from game.codex import registrar_encontro
    registrar_encontro(session, player, monstro.id)
    player.em_combate_turnos = 0
    player.em_combate_proficiencia_ganha = 0
    player.em_combate_hp_monstro = monstro.hp
    session.commit()

    vig_atual, vig_max = player.vig_atual, player.vig_max
    mana_atual, mana_max = player.mana_atual, player.mana_max
    texto = (
        f"💀 *{local.nome}*\n\n"
        f"⚔️ *CONFRONTO DE BOSS*\n\n"
        f"🔴 *{monstro.nome}* — Nv.{monstro.nivel} ({monstro.papel})\n"
        f"❤️ {monstro.hp}/{monstro.hp}\n{_barra_hp(monstro.hp, monstro.hp, cheio='🟥')}\n\n"
    )
    if monstro.motivacao:
        texto += f"_{monstro.motivacao}_\n\n"
    texto += (
        f"🗡️ Golpe: {monstro.golpe_especial}\n\n"
        f"⚡ Seu Vigor: {vig_atual}/{vig_max}"
        + (f"\n🔷 Mana: {mana_atual}/{mana_max}" if mana_max else "")
    )
    botoes = [[InlineKeyboardButton("⚔️ Atacar", callback_data="atacar")]]
    if mana_max:
        botoes[0].append(InlineKeyboardButton("✨ Magias", callback_data="menu_magias"))
    if verificar_pode_poupar(monstro, monstro.hp, monstro.hp):
        botoes.append([InlineKeyboardButton("🕊️ Poupar", callback_data="poupar")])
    botoes.append([InlineKeyboardButton("🏃 Fugir", callback_data="fugir")])
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))
