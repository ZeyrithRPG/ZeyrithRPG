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

ICONE_CATEGORIA_MISSAO = {
    "Combate (Grind)": "⚔️", "Coleta": "🧺", "Elite": "🐲",
    "Social": "🗣️", "Exploração": "🗺️", "Crafting": "🔨",
}


async def menu_missoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    dados = query.data.split("_", 2)
    categoria_filtro = dados[2] if len(dados) > 2 else None

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

    principais = [m for m in disponiveis if m.is_principal]
    secundarias = [m for m in disponiveis if not m.is_principal]
    por_categoria = {}
    for m in secundarias:
        por_categoria.setdefault(m.categoria or "Outras", []).append(m)

    if not categoria_filtro:
        texto = f"📜 *Missões — {tier_nome}*\n🏛️ Honra com {faccao}: {honra}\n"
        botoes = []

        if em_andamento:
            texto += "\n*Em andamento:*\n"
            for pq in em_andamento:
                m = session.query(Missao).filter_by(id=pq.quest_id).first()
                if not m:
                    continue
                texto += f"🔸 {m.nome}\n"
                botoes.append([InlineKeyboardButton(f"✅ Entregar: {m.nome}", callback_data=f"miss_entregar_{m.id}")])

        if principais:
            texto += "\n*Missão Principal:*\n"
            for m in principais:
                texto += f"⭐ {m.nome}\n_{m.objetivo}_\n"
                botoes.append([InlineKeyboardButton(f"⭐ Aceitar: {m.nome}", callback_data=f"miss_aceitar_{m.id}")])

        texto += "\n*Categorias:*"
        for cat, lista in sorted(por_categoria.items()):
            icone_cat = ICONE_CATEGORIA_MISSAO.get(cat, "📋")
            botoes.append([InlineKeyboardButton(
                f"{icone_cat} {cat} ({len(lista)})", callback_data=f"menu_missoes_{cat}",
            )])

        botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")])
        session.close()
        await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))
        return

    lista_cat = por_categoria.get(categoria_filtro, [])
    icone_cat = ICONE_CATEGORIA_MISSAO.get(categoria_filtro, "📋")
    texto = f"{icone_cat} *{categoria_filtro} — {tier_nome}*\n🏛️ Honra com {faccao}: {honra}\n"
    botoes = []
    for m in lista_cat:
        texto += f"\n➖➖➖➖➖➖➖➖➖➖\n📜 *{m.nome}*\n"
        texto += f"_{m.objetivo}_\n"
        if m.requisito_honra:
            texto += f"🏛️ {m.requisito_honra}\n"
        if m.npc_fonte:
            texto += f"🗣️ Fonte: {m.npc_fonte}\n"
        recompensa_txt = str(m.recompensa) if m.recompensa else "0"
        texto += f"💰 {recompensa_txt}"
        if not any(c.isdigit() for c in recompensa_txt):
            pass
        elif "Ouro" not in recompensa_txt:
            texto += " Ouro"
        texto += "\n"
        if m.recompensa_extra:
            texto += f"🎁 {m.recompensa_extra}\n"
        botoes.append([InlineKeyboardButton(f"Aceitar: {m.nome}", callback_data=f"miss_aceitar_{m.id}")])
    botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu_missoes")])
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def cb_aceitar_missao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
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
    query.data = "menu_missoes"  # evita que o ID da missao seja lido como categoria
    await menu_missoes(update, context)


async def cb_entregar_missao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    missao_id = int(query.data.split("_")[-1])
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    try:
        ouro, honra_ganha, faccao, recompensa_extra, niveis_subidos = completar_missao(session, player, missao_id)
        await query.answer()
        texto = f"✅ *Missão concluída!*\n\n💰 +{ouro} Ouro"
        if honra_ganha:
            texto += f"\n🏛️ +{honra_ganha} Honra com {faccao}"
        if recompensa_extra:
            texto += f"\n🎁 {recompensa_extra}"
        if niveis_subidos:
            texto += f"\n\n🎉 *LEVEL UP! Você chegou ao Nível {niveis_subidos[-1]}!*"
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
    dados = query.data.split("_", 2)
    faccao_filtro = dados[2] if len(dados) > 2 else None

    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    from db.models import PlayerReputacaoFaccao, Faccao
    todas_faccoes = session.query(Faccao).order_by(Faccao.id).all()
    reps = {r.faccao: r.pontos for r in session.query(PlayerReputacaoFaccao).filter_by(player_id=player.id).all()}

    if not faccao_filtro:
        await query.answer()
        titulos = listar_titulos_do_player(session, player)
        texto = "🏛️ *Facções*\n\nEscolha uma pra ver detalhes:"
        botoes = []
        for f in todas_faccoes:
            honra = reps.get(f.faccao_dominante, 0)
            botoes.append([InlineKeyboardButton(
                f"{f.faccao_dominante} (Honra: {honra})", callback_data=f"menu_faccoes_{f.id}",
            )])
        botoes.append([InlineKeyboardButton("🏆 Ver Títulos", callback_data="menu_titulos")])
        botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")])
        session.close()
        await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))
        return

    f = session.query(Faccao).filter_by(id=int(faccao_filtro)).first()
    session.close()
    if not f:
        await query.answer("Facção não encontrada.", show_alert=True)
        return

    await query.answer()
    honra = reps.get(f.faccao_dominante, 0)
    texto = (
        f"🏛️ *{f.faccao_dominante}*\n"
        f"_{f.reino_provincia} · {f.tiers_cobertos}_\n\n"
        f"👑 Capital: {f.capital}\n"
        f"🎖️ Líder: {f.lider}\n"
        f"🐺 Ameaça local: {f.culto_ameaca}\n"
        f"🏛️ Sua Honra: {honra}\n"
    )
    if honra >= 50:
        texto += f"\n🔓 _Segredo revelado: {f.segredo}_"
    else:
        texto += "\n🔒 _Segredo bloqueado — precisa de Honra 50+ pra revelar._"

    await query.edit_message_text(
        texto, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_faccoes")]]
        ),
    )


async def menu_titulos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    titulos = listar_titulos_do_player(session, player)
    session.close()

    texto = "🏆 *Títulos Conquistados*\n\n"
    if titulos:
        for t in titulos:
            texto += f"🏆 *{t.nome}*\n_{t.bonus}_\n\n"
    else:
        texto += "Nenhum título ainda."

    await query.edit_message_text(
        texto, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_faccoes")]]
        ),
    )
    await query.edit_message_text(
        texto, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
        ),
    )
