"""
Fase 3 — Comércio: comprar/vender Arma e Armadura, Crafting (forjar receitas).
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.connection import get_session
from db.models import Player, Local, Receita
from game.economia import (
    listar_equipamento, comprar_item, vender_item, listar_receitas,
    verificar_forja, forjar_item, ErroEconomia, _parse_qtd, _normalizar,
)

ICONE_CATEGORIA = {"arma": "⚔️", "armadura": "🛡️"}
ICONE_TIPO_ITEM = {
    "Espada": "🗡️", "Machado": "🪓", "Maca": "🔨", "Maça": "🔨",
    "Arco": "🏹", "Cetro": "🪄", "Adaga": "🔪",
    "Peitoral": "🛡️", "Escudo": "🔰", "Elmo": "⛑️",
    "Manopla": "🧤", "Luvas": "🧤", "Bota": "👢", "Calca": "👖", "Calça": "👖",
    "Amuleto": "📿", "Anel": "💍", "Colar": "📿", "Talismã": "🔮", "Talisma": "🔮",
    "Pena": "🪶", "Vial": "🧪", "Bolsa": "👝",
}


def _icone_tipo(tipo_ou_slot):
    if tipo_ou_slot in ICONE_TIPO_ITEM:
        return ICONE_TIPO_ITEM[tipo_ou_slot]
    alvo = _normalizar(tipo_ou_slot)
    for chave, icone in ICONE_TIPO_ITEM.items():
        if _normalizar(chave) == alvo:
            return icone
    return "❔"
ICONE_MATERIAL_PADRAO = "🧱"


def _icone_material(session, nome_material):
    from db.models import Material
    mat = session.query(Material).filter_by(nome=nome_material).first()
    return mat.icone if (mat and mat.icone) else ICONE_MATERIAL_PADRAO


def _tier_do_player(session, player):
    local = None
    if player.local_atual:
        local = session.query(Local).filter_by(nome=player.local_atual).first()
    # tier do personagem vem do proprio tier_mais_alto_alcancado -- usa o Tier por indice
    from db.models import Tier
    tiers = session.query(Tier).order_by(Tier.id).all()
    idx = max(0, min(player.tier_mais_alto_alcancado - 1, len(tiers) - 1))
    return tiers[idx].nome if tiers else "Sucata Enferrujada"


def _ferreiro_da_cidade(session, tier_nome):
    from db.models import Cidade, NPC
    cidades = session.query(Cidade).all()
    cidade = next((c for c in cidades if c.tiers_cobertos and tier_nome in c.tiers_cobertos), None)
    if not cidade:
        return None
    npc = (
        session.query(NPC)
        .filter(NPC.cidade == cidade.nome, NPC.titulo_ocupacao.like("%Ferreiro%"))
        .first()
    )
    return npc


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
    dados = query.data.split("_")
    categoria = dados[2]
    tipo_filtro = "_".join(dados[3:]) if len(dados) > 3 else None

    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    tier_nome = _tier_do_player(session, player)
    itens = listar_equipamento(session, tier_nome, categoria)
    ferreiro = _ferreiro_da_cidade(session, tier_nome)
    nome_vendedor = ferreiro.nome if ferreiro else "Comerciante local"

    icone = ICONE_CATEGORIA[categoria]

    # agrupa por Tipo/Slot (Espada, Machado, Peitoral, etc) -- Arma usa 'tipo', Armadura usa 'slot'
    por_tipo = {}
    for item in itens:
        chave = item.tipo if categoria == "arma" else item.slot
        por_tipo.setdefault(chave, []).append(item)

    if not tipo_filtro:
        # mostra so os TIPOS disponiveis, nao os 20 itens de uma vez
        texto = f"{icone} *{nome_vendedor}*\n_{categoria.capitalize()}s de {tier_nome}_\n💰 Seu Ouro: {player.ouro}\n\n"
        texto += "Escolha um tipo:"
        botoes = []
        for tipo, lista in sorted(por_tipo.items()):
            icone_tipo = _icone_tipo(tipo)
            botoes.append([InlineKeyboardButton(
                f"{icone_tipo} {tipo} ({len(lista)} variações)",
                callback_data=f"loja_comprar_{categoria}_{tipo}",
            )])
        botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu_comercio")])
        session.close()
        await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))
        return

    lista_tipo = por_tipo.get(tipo_filtro, [])
    icone_tipo = _icone_tipo(tipo_filtro)
    texto = f"{icone} *{nome_vendedor} — {icone_tipo} {tipo_filtro}*\n💰 Seu Ouro: {player.ouro}\n"
    botoes = []
    for item in lista_tipo:
        if categoria == "arma":
            stat_txt = f"⚔️ Dano {item.dano_comum}"
        else:
            stat_txt = f"🛡️ Defesa {item.defesa_comum}"
        texto += f"\n➖➖➖➖➖➖➖➖➖➖\n{icone_tipo} *{item.variacao}*\n"
        texto += f"_STATUS_\n{stat_txt}\n💰 {item.preco_compra} Ouro\n"
        if item.efeito_especial:
            texto += f"↳ _{item.efeito_especial}_\n"
        if item.lore:
            texto += f"_{item.lore}_\n"
        botoes.append([InlineKeyboardButton(
            f"Comprar {item.variacao} ({item.preco_compra}💰)",
            callback_data=f"loja_comprarid_{categoria}_{item.id}",
        )])
    botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data=f"loja_comprar_{categoria}")])
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def confirmar_compra(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, _, categoria, item_id = query.data.split("_", 3)
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    tipo_item_comprado = None
    try:
        inv = comprar_item(session, player, int(item_id), categoria)
        await query.answer(f"✅ Comprado: {inv.nome_item}!", show_alert=True)
        from db.models import Arma, Armadura
        Modelo = Arma if categoria == "arma" else Armadura
        item_real = session.query(Modelo).filter_by(id=int(item_id)).first()
        if item_real:
            tipo_item_comprado = item_real.tipo if categoria == "arma" else item_real.slot
    except ErroEconomia as e:
        await query.answer(f"❌ {e}", show_alert=True)
    session.close()

    # corrige query.data pro formato de NAVEGACAO antes de re-chamar listar_compra --
    # senao o "id" da compra e interpretado por engano como se fosse um "tipo"
    if tipo_item_comprado:
        query.data = f"loja_comprar_{categoria}_{tipo_item_comprado}"
    else:
        query.data = f"loja_comprar_{categoria}"
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

    texto = f"🔨 *Forjar — {tier_nome}*\n💰 Seu Ouro: {player.ouro}\n"
    botoes = []
    for r in receitas[:20]:
        pode, motivo, _ = verificar_forja(session, player, r.id)
        marca = "🔓" if pode else "🔒"

        item_real = None
        if categoria_filtro != "acessorios":
            from db.models import Arma, Armadura
            eh_armadura = r.tipo_slot in ("Peitoral", "Escudo", "Elmo", "Luvas", "Bota", "Calça", "Manopla")
            if eh_armadura:
                candidatos = session.query(Armadura).filter_by(tier=tier_nome).order_by(Armadura.id).all()
                item_real = next((a for a in candidatos if _normalizar(a.slot) == _normalizar(r.tipo_slot)), None)
            else:
                candidatos = session.query(Arma).filter_by(tier=tier_nome).order_by(Arma.id).all()
                item_real = next((a for a in candidatos if _normalizar(a.tipo) == _normalizar(r.tipo_slot)), None)

        nome_exibido = item_real.variacao if item_real else r.tipo_slot
        icone_tipo_item = _icone_tipo(r.tipo_slot)
        texto += f"\n➖➖➖➖➖➖➖➖➖➖\n{marca} {icone_tipo_item} *{nome_exibido}*\n"

        if item_real:
            if hasattr(item_real, "dano_comum"):
                texto += f"_STATUS_\n⚔️ Dano {item_real.dano_comum}\n"
            else:
                texto += f"_STATUS_\n🛡️ Defesa {item_real.defesa_comum}\n"
        texto += f"💰 {r.custo_base_ouro or 0} Ouro\n"

        materiais_linhas = []
        for campo in (r.material_base_1, r.material_base_2):
            if not campo:
                continue
            nome, qtd = _parse_qtd(campo)
            icone_mat = _icone_material(session, nome)
            materiais_linhas.append(f"{icone_mat} {nome} — {qtd}x")
        if materiais_linhas:
            texto += "_MATERIAIS NECESSÁRIOS_\n" + "\n".join(materiais_linhas) + "\n"

        if r.efeito and r.categoria == "Acessório":
            texto += f"↳ _{r.efeito}_\n"
        elif item_real and item_real.lore:
            texto += f"_{item_real.lore}_\n"

        botoes.append([InlineKeyboardButton(f"Forjar {nome_exibido}", callback_data=f"loja_forjar_{r.id}")])
    botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data="loja_crafting")])
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def confirmar_forja(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    receita_id = int(query.data.split("_")[-1])
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    categoria_receita = None
    try:
        receita = session.query(Receita).filter_by(id=receita_id).first()
        categoria_receita = receita.categoria if receita else None
        item = forjar_item(session, player, receita_id)
        await query.answer(f"✅ Forjado: {item.nome_item}!", show_alert=True)
    except ErroEconomia as e:
        await query.answer(f"❌ {e}", show_alert=True)
    session.close()

    # corrige query.data pro formato de NAVEGACAO antes de re-chamar menu_crafting
    query.data = "loja_crafting_acessorios" if categoria_receita == "Acessório" else "loja_crafting_armaduras"
    await menu_crafting(update, context)
