"""
Fase 6 — Mapa: listar locais (respeitando Secreto), viajar, Covil de Boss.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.connection import get_session
from db.models import Player, Local, Monstro
from game.mapa import listar_locais_visiveis, monstro_do_covil
from game.combat import verificar_pode_poupar

ICONE_TIPO_LOCAL = {
    "Cidade": "🏰", "Estrada Perigosa": "🛤️", "Mina": "⛏️", "Dungeon": "🕸️",
    "Ruina": "🏛️", "Floresta Perigosa": "🌲", "Caverna": "🕳️",
    "Planicie Selvagem": "🌾", "Fenda": "🌋", "Campo de Batalha": "⚔️",
    "Pantano": "🐊", "Covil de Boss": "💀", "Ritual": "🔮", "Portal": "🌀",
    "Local Secreto": "❓",
}
BARRA_PERIGO = {1: "🟢", 2: "🟢", 3: "🟡", 4: "🟠", 5: "🔴"}


from game.ui_utils import barra as _barra_hp


async def menu_mapa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    locais = listar_locais_visiveis(session, player)

    texto = f"🗺️ *Mapa*\n📍 Você está em: {player.local_atual or 'Vila Inicial'}\n\n"
    botoes = []
    for local in locais:
        icone = ICONE_TIPO_LOCAL.get(local.tipo, "📍")
        barra = BARRA_PERIGO.get(local.perigo, "🟡") * (local.perigo or 1)
        marca = "📍 " if local.nome == player.local_atual else ""
        nivel_txt = f" · Nv.{local.nivel_ref}" if local.nivel_ref else ""

        if getattr(local, "travado", False):
            texto += f"🔒 {local.nome}{nivel_txt} — precisa de Nível {local.nivel_ref - 15}+\n"
            continue

        texto += f"{icone} {marca}{local.nome}{nivel_txt} — {barra}\n"
        if local.nome != player.local_atual:
            botoes.append([InlineKeyboardButton(f"Viajar: {local.nome}", callback_data=f"mapa_ir_{local.id}")])

    botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")])
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def viajar_local(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    local_id = int(query.data.split("_")[-1])
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    local = session.query(Local).filter_by(id=local_id).first()

    if not local:
        await query.answer("Local não encontrado.", show_alert=True)
        session.close()
        return

    if local.nivel_ref and player.nivel and local.nivel_ref > (player.nivel + 15):
        await query.answer(
            f"🔒 Você precisa de Nível {local.nivel_ref - 15}+ pra ir até {local.nome}.",
            show_alert=True,
        )
        session.close()
        return

    player.local_atual = local.nome
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
             [InlineKeyboardButton("⬅️ Voltar ao Mapa", callback_data="menu_mapa")]]
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
                [[InlineKeyboardButton("⬅️ Voltar ao Mapa", callback_data="menu_mapa")]]
            ),
        )
        return

    player.em_combate_monstro_id = monstro.id
    player.em_combate_hp_monstro = monstro.hp
    session.commit()

    vig_atual, vig_max = player.vig_atual, player.vig_max
    mana_atual, mana_max = player.mana_atual, player.mana_max
    texto = (
        f"💀 *{local.nome}*\n\n"
        f"⚔️ *CONFRONTO DE BOSS*\n\n"
        f"🔴 *{monstro.nome}* — Nv.{monstro.nivel} ({monstro.papel})\n"
        f"❤️ {monstro.hp}/{monstro.hp}\n{_barra_hp(monstro.hp, monstro.hp, cheio='🟥')}\n\n"
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
