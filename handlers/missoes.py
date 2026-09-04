"""
Fase 5 — Missões e Facções/Títulos.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.connection import get_session
from db.models import Player, Tier, PlayerQuest, Missao
from game.missoes import (
    listar_missoes_disponiveis, aceitar_missao, completar_missao,
    honra_do_player, TIER_PARA_FACCAO, ErroMissao,
)
from game.titulos import listar_titulos_do_player


def _tier_do_player(session, player):
    tiers = session.query(Tier).order_by(Tier.id).all()
    idx = max(0, min(player.tier_mais_alto_alcancado - 1, len(tiers) - 1))
    return tiers[idx].nome if tiers else "Sucata Enferrujada"


# ---------- Menu de Missões ----------

async def menu_missoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    tier_nome = _tier_do_player(session, player)
    faccao = TIER_PARA_FACCAO.get(tier_nome)
    honra = honra_do_player(session, player, faccao) if faccao else 0

    disponiveis = listar_missoes_disponiveis(session, player, tier_nome)
    em_andamento = (
        session.query(PlayerQuest)
        .filter_by(player_id=player.id, status="em_andamento")
        .all()
    )

    texto = f"📜 *Missões — {tier_nome}*\n🏛️ Honra com {faccao}: {honra}\n\n"
    botoes = []

    if em_andamento:
        texto += "*Em andamento:*\n"
        for pq in em_andamento:
            m = session.query(Missao).filter_by(id=pq.quest_id).first()
            if not m:
                continue
            texto += f"🔸 {m.nome}\n"
            botoes.append([InlineKeyboardButton(f"✅ Entregar: {m.nome}", callback_data=f"miss_entregar_{m.id}")])

    if disponiveis:
        texto += "\n*Disponíveis:*\n"
        for m in disponiveis[:10]:
            marca = "⭐" if m.is_principal else ""
            texto += f"{marca} {m.nome} ({m.categoria or 'Principal'})\n"
            botoes.append([InlineKeyboardButton(f"Aceitar: {m.nome}", callback_data=f"miss_aceitar_{m.id}")])

    if not em_andamento and not disponiveis:
        texto += "Nenhuma missão nova disponível aqui agora."

    botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")])
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def cb_aceitar_missao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    missao_id = int(query.data.split("_")[-1])
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    try:
        aceitar_missao(session, player, missao_id)
        await query.answer("✅ Missão aceita!", show_alert=True)
    except ErroMissao as e:
        await query.answer(f"❌ {e}", show_alert=True)
    session.close()
    await menu_missoes(update, context)


async def cb_entregar_missao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    missao_id = int(query.data.split("_")[-1])
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    try:
        ouro, honra_ganha, faccao, recompensa_extra = completar_missao(session, player, missao_id)
        texto = f"✅ *Missão concluída!*\n\n💰 +{ouro} Ouro"
        if honra_ganha:
            texto += f"\n🏛️ +{honra_ganha} Honra com {faccao}"
        if recompensa_extra:
            texto += f"\n🎁 {recompensa_extra}"
        session.close()
        await query.edit_message_text(
            texto, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_missoes")]]
            ),
        )
    except ErroMissao as e:
        await query.answer(f"❌ {e}", show_alert=True)
        session.close()


# ---------- Facções & Títulos ----------

async def menu_faccoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    from db.models import PlayerReputacaoFaccao
    reps = session.query(PlayerReputacaoFaccao).filter_by(player_id=player.id).all()
    titulos = listar_titulos_do_player(session, player)

    texto = "🏛️ *Facções & Títulos*\n\n*Reputação:*\n"
    if reps:
        for r in reps:
            texto += f"  {r.faccao}: {r.pontos}\n"
    else:
        texto += "  Nenhuma reputação ainda.\n"

    texto += "\n*Títulos conquistados:*\n"
    if titulos:
        for t in titulos:
            texto += f"  🏆 {t.nome}\n"
    else:
        texto += "  Nenhum título ainda.\n"

    session.close()
    await query.edit_message_text(
        texto, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
        ),
    )
