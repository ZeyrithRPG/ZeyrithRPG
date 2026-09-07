"""
Codex — Monstros (Knowledge 0-5 progressivo), Locais, Materiais.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.connection import get_session
from db.models import Player, Monstro, Tier
from game.codex import nivel_do_jogador, info_revelada, NIVEL_MAX

ICONE_PAPEL = {"Comum": "⚪", "Elite": "🟣", "Boss": "🔴", "Cosmico": "🌌"}


def _barra_knowledge(nivel):
    return "🟨" * nivel + "⬛" * (NIVEL_MAX - nivel)


async def menu_codex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    texto = "📖 *Codex*\n\nO que você já descobriu sobre o mundo."
    botoes = [
        [InlineKeyboardButton("🐾 Bestiário", callback_data="codex_bestiario")],
        [InlineKeyboardButton("🗺️ Locais", callback_data="codex_locais")],
        [InlineKeyboardButton("🧱 Materiais", callback_data="codex_materiais")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")],
    ]
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


# ---------- Bestiário ----------

async def codex_bestiario_tiers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    tiers = session.query(Tier).order_by(Tier.id).all()
    texto = "🐾 *Bestiário — por Tier*\n\nEscolha um Tier:"
    botoes = []
    for t in tiers:
        monstros_tier = session.query(Monstro).filter_by(tier=t.nome).all()
        total = len(monstros_tier)
        descobertos = sum(
            1 for m in monstros_tier if nivel_do_jogador(session, player, m.id) > 0
        )
        botoes.append([InlineKeyboardButton(
            f"{t.nome} ({descobertos}/{total})", callback_data=f"codex_bestiario_{t.id}",
        )])
    botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu_codex")])
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def codex_bestiario_lista(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tier_id = int(query.data.split("_")[-1])
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    tier = session.query(Tier).filter_by(id=tier_id).first()

    monstros = session.query(Monstro).filter_by(tier=tier.nome).order_by(Monstro.nivel).all()
    texto = f"🐾 *Bestiário — {tier.nome}*\n\n"
    botoes = []
    for m in monstros:
        nivel_kn = nivel_do_jogador(session, player, m.id)
        if nivel_kn == 0:
            texto += "❓❓❓ (não descoberto)\n"
        else:
            icone = ICONE_PAPEL.get(m.papel, "⚪")
            texto += f"{icone} {m.nome} — {_barra_knowledge(nivel_kn)}\n"
            botoes.append([InlineKeyboardButton(m.nome, callback_data=f"codex_monstro_{m.id}")])
    botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data="codex_bestiario")])
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def codex_monstro_detalhe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    monstro_id = int(query.data.split("_")[-1])
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    monstro = session.query(Monstro).filter_by(id=monstro_id).first()
    nivel_kn = nivel_do_jogador(session, player, monstro_id)
    info = info_revelada(monstro, nivel_kn)
    tier_nome = monstro.tier
    session.close()

    texto = f"📖 *Codex — {_barra_knowledge(nivel_kn)} (Nv.Knowledge {nivel_kn}/{NIVEL_MAX})*\n\n"

    if "nome" in info:
        icone = ICONE_PAPEL.get(info["papel"], "⚪")
        texto += f"{icone} *{info['nome']}* — Nv.{info['nivel_monstro']} ({info['papel']})\n"
        texto += f"🏔️ Tier: {tier_nome}\n\n"
    else:
        texto += "❓❓❓ *Desconhecido*\n\nDerrote-o em combate pra começar a descobrir."

    if "hp" in info:
        texto += f"❤️ HP: {info['hp']} · ⚔️ Dano: {info['dano']} · 🛡️ Defesa: {info['defesa']}\n"
        texto += f"🗡️ Golpe: {info['golpe_especial']}\n\n"
    elif "nome" in info:
        texto += "❓ HP/Dano/Defesa — vença 1x pra descobrir\n\n"

    if "efeito_mecanico" in info:
        texto += f"⚙️ {info['efeito_mecanico']}\n"
        if info.get("materiais_dropados"):
            texto += f"🧱 Dropa: {info['materiais_dropados']}\n"
        texto += "\n"
    elif "hp" in info:
        texto += "❓ Efeito/Materiais — vença 2x pra descobrir\n\n"

    if "fraqueza" in info:
        texto += f"🎯 Fraqueza: {info['fraqueza']}\n\n"
    elif "efeito_mecanico" in info:
        texto += "❓ Fraqueza — vença 3x pra descobrir\n\n"

    if "motivacao" in info:
        texto += f"_{info['motivacao']}_\n"
        if info.get("loot_unico"):
            texto += f"\n🏆 Loot único: {info['loot_unico']}"
    elif "fraqueza" in info:
        texto += "❓ Lore/Motivação — vença 5x pra descobrir"

    await query.edit_message_text(
        texto, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Voltar", callback_data="codex_bestiario")]]
        ),
    )


# ---------- Locais (descoberto = ja visitou) ----------

async def codex_locais(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from db.models import Local
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    locais_visitados = set((player.locais_visitados or "").split("|"))
    if player.local_atual:
        locais_visitados.add(player.local_atual)
    locais_visitados.discard("")

    todos = session.query(Local).order_by(Local.id).all()
    texto = "🗺️ *Codex — Locais*\n\n"
    for l in todos:
        if l.nome in locais_visitados:
            texto += f"📍 {l.nome} — {l.tipo}\n"
        else:
            texto += "❓❓❓\n"
    session.close()
    await query.edit_message_text(
        texto, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_codex")]]
        ),
    )


# ---------- Materiais (descoberto = ja teve no inventario) ----------

async def codex_materiais(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from db.models import Material, PlayerInventario
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    nomes_conhecidos = {
        i.nome_item for i in session.query(PlayerInventario)
        .filter_by(player_id=player.id, tipo_item="material").all()
    }

    tier_nome = None
    from db.models import Tier
    tiers = session.query(Tier).order_by(Tier.id).all()
    idx = max(0, min(player.tier_mais_alto_alcancado - 1, len(tiers) - 1))
    tier_nome = tiers[idx].nome if tiers else None

    materiais = session.query(Material).filter_by(tier=tier_nome).all()
    texto = f"🧱 *Codex — Materiais ({tier_nome})*\n\n"
    for m in materiais:
        if m.nome in nomes_conhecidos:
            texto += f"{m.icone or '🧱'} {m.nome} — {m.categoria}\n"
        else:
            texto += "❓❓❓\n"
    session.close()
    await query.edit_message_text(
        texto, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_codex")]]
        ),
    )
