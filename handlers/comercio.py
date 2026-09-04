"""
Fase 3 — Comércio: comprar/vender Arma e Armadura, Crafting (forjar receitas).
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.connection import get_session
from db.models import Player, Local, Receita
from game.economia import (
    listar_equipamento, comprar_item, vender_item, listar_receitas,
    verificar_forja, forjar_item, ErroEconomia,
)

ICONE_CATEGORIA = {"arma": "⚔️", "armadura": "🛡️"}


def _tier_do_player(session, player):
    local = None
    if player.local_atual:
        local = session.query(Local).filter_by(nome=player.local_atual).first()
    # tier do personagem vem do proprio tier_mais_alto_alcancado -- usa o Tier por indice
    from db.models import Tier
    tiers = session.query(Tier).order_by(Tier.id).all()
    idx = max(0, min(player.tier_mais_alto_alcancado - 1, len(tiers) - 1))
    return tiers[idx].nome if tiers else "Sucata Enferrujada"


# ---------- Menu principal de Comercio ----------

async def menu_comercio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    botoes = [
        [InlineKeyboardButton("⚔️ Comprar Arma", callback_data="loja_comprar_arma"),
         InlineKeyboardButton("🛡️ Comprar Armadura", callback_data="loja_comprar_armadura")],
        [InlineKeyboardButton("💰 Vender Item", callback_data="loja_vender")],
        [InlineKeyboardButton("🔨 Forjar (Crafting)", callback_data="loja_crafting")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")],
    ]
    await query.edit_message_text(
        "🏪 *Comércio*\n\nCompre, venda ou forje equipamento do seu Tier atual.",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes),
    )


# ---------- Comprar ----------

async def listar_compra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    categoria = "arma" if query.data == "loja_comprar_arma" else "armadura"
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    tier_nome = _tier_do_player(session, player)
    itens = listar_equipamento(session, tier_nome, categoria)

    icone = ICONE_CATEGORIA[categoria]
    texto = f"{icone} *{categoria.capitalize()}s de {tier_nome}*\n💰 Seu Ouro: {player.ouro}\n\n"
    botoes = []
    for item in itens[:15]:
        texto += f"{icone} {item.variacao} — {item.preco_compra} Ouro\n"
        botoes.append([InlineKeyboardButton(
            f"Comprar {item.variacao} ({item.preco_compra}💰)",
            callback_data=f"loja_comprarid_{categoria}_{item.id}",
        )])
    botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu_comercio")])
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def confirmar_compra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, _, categoria, item_id = query.data.split("_", 3)
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    try:
        inv = comprar_item(session, player, int(item_id), categoria)
        await query.answer(f"✅ Comprado: {inv.nome_item}!", show_alert=True)
    except ErroEconomia as e:
        await query.answer(f"❌ {e}", show_alert=True)
    session.close()
    await listar_compra(update, context)


# ---------- Vender ----------

async def listar_venda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    from db.models import PlayerInventario, Arma, Armadura
    itens = (
        session.query(PlayerInventario)
        .filter(PlayerInventario.player_id == player.id,
                PlayerInventario.tipo_item.in_(["arma", "armadura"]),
                PlayerInventario.equipado == False)  # noqa: E712
        .all()
    )
    texto = f"💰 *Vender Item*\n💰 Seu Ouro: {player.ouro}\n\n"
    botoes = []
    if not itens:
        texto += "Você não tem nada pra vender (itens equipados não entram)."
    for inv in itens[:15]:
        Modelo = Arma if inv.tipo_item == "arma" else Armadura
        ref = session.query(Modelo).filter_by(id=inv.item_ref_id).first()
        preco = ref.preco_venda_mercador if ref else 0
        texto += f"{inv.nome_item} — vende por {preco} Ouro\n"
        botoes.append([InlineKeyboardButton(
            f"Vender {inv.nome_item} ({preco}💰)", callback_data=f"loja_venderid_{inv.id}",
        )])
    botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu_comercio")])
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def confirmar_venda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    inv_id = int(query.data.split("_")[-1])
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    try:
        preco = vender_item(session, player, inv_id)
        await query.answer(f"✅ Vendido por {preco} Ouro!", show_alert=True)
    except ErroEconomia as e:
        await query.answer(f"❌ {e}", show_alert=True)
    session.close()
    await listar_venda(update, context)


# ---------- Crafting ----------

async def menu_crafting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    categoria_filtro = query.data.split("_", 2)[-1] if query.data.startswith("loja_crafting_") else None

    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    tier_nome = _tier_do_player(session, player)
    todas_receitas = listar_receitas(session, tier_nome)

    if not categoria_filtro:
        n_arma = sum(1 for r in todas_receitas if r.categoria != "Acessório")
        n_acessorio = sum(1 for r in todas_receitas if r.categoria == "Acessório")
        session.close()
        botoes = [
            [InlineKeyboardButton(f"⚔️ Armas & Armaduras ({n_arma})", callback_data="loja_crafting_armaduras")],
        ]
        if n_acessorio:
            botoes.append([InlineKeyboardButton(f"💍 Acessórios ({n_acessorio})", callback_data="loja_crafting_acessorios")])
        botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu_comercio")])
        await query.edit_message_text(
            f"🔨 *Forjar — {tier_nome}*\n\nEscolha uma categoria:",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes),
        )
        return

    if categoria_filtro == "acessorios":
        receitas = [r for r in todas_receitas if r.categoria == "Acessório"]
    else:
        receitas = [r for r in todas_receitas if r.categoria != "Acessório"]

    texto = f"🔨 *Forjar — {tier_nome}*\n💰 Seu Ouro: {player.ouro}\n\n"
    botoes = []
    for r in receitas[:20]:
        pode, motivo, _ = verificar_forja(session, player, r.id)
        marca = "✅" if pode else "❌"
        texto += f"{marca} *{r.tipo_slot}*\n"
        texto += f"   💰 {r.custo_base_ouro or 0} Ouro\n"
        if r.material_base_1:
            texto += f"   🧱 {r.material_base_1}\n"
        if r.material_base_2:
            texto += f"   🧱 {r.material_base_2}\n"
        if r.efeito and r.categoria == "Acessório":
            texto += f"   ↳ _{r.efeito}_\n"
        texto += "\n"
        botoes.append([InlineKeyboardButton(f"Forjar {r.tipo_slot}", callback_data=f"loja_forjar_{r.id}")])
    botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data="loja_crafting")])
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def confirmar_forja(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    receita_id = int(query.data.split("_")[-1])
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    try:
        item = forjar_item(session, player, receita_id)
        await query.answer(f"✅ Forjado: {item.nome_item}!", show_alert=True)
    except ErroEconomia as e:
        await query.answer(f"❌ {e}", show_alert=True)
    session.close()
    await menu_crafting(update, context)
