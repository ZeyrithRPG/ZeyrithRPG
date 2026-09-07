"""
Fase 3 — Comércio: comprar/vender Arma e Armadura, Crafting (forjar receitas).
Totalmente alinhado às regras da planilha oficial:
- Catálogo numerado e grade compacta de compra
- Balcão de penhores (40% vitrine) com venda única e [ Vender Tudo ]
- Proteção backend contra venda de itens equipados e excesso de mochila
- Forja dividida em Armas, Armaduras e Acessórios
- Contadores visuais de materiais com checkmarks
- Desbloqueio e compra de diagramas de receitas
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.connection import get_session
from db.models import Player, Local, Receita, Arma, Armadura, Material, PlayerInventario
from game.economia import (
    listar_equipamento, comprar_item, vender_item, vender_tudo,
    listar_receitas, verificar_forja, forjar_item, ErroEconomia,
    slots_mochila_ocupados, receita_desbloqueada, comprar_diagrama,
    calcular_preco_diagrama, obter_materiais_receita, _parse_qtd, _normalizar,
    calcular_preco_compra_item, calcular_custo_reparo, reparar_item,
)

ICONE_CATEGORIA = {"arma": "⚔️", "armadura": "🛡️"}
ICONE_TIPO_ITEM = {
    "Espada": "🗡️", "Machado": "🪓", "Maca": "🔨", "Maça": "🔨",
    "Arco": "🏹", "Cetro": "🪄", "Adaga": "🔪",
    "Peitoral": "🛡️", "Escudo": "🔰", "Elmo": "⛑️",
    "Manopla": "🧤", "Luvas": "🧤", "Bota": "👢", "Calca": "👖", "Calça": "👖",
    "Amuleto": "📿", "Anel": "💍", "Colar": "📿", "Talismã": "🔮", "Talisma": "🔮",
    "Pena": "🪶", "Vial": "🧪", "Bolsa": "👝",
    "Faca": "🔪", "Picareta": "⛏️", "Comida": "🍖", "Bebida": "🍺",
    "Poção": "🧪", "Pocao": "🧪", "Ferramenta": "🛠️", "Acessório": "💍", "Acessorio": "💍",
    "Grimório": "📖", "Grimorio": "📖",
}


def _icone_tipo(tipo_ou_slot):
    if not tipo_ou_slot:
        return "📦"
    if tipo_ou_slot in ICONE_TIPO_ITEM:
        return ICONE_TIPO_ITEM[tipo_ou_slot]
    alvo = _normalizar(tipo_ou_slot).lower()
    for chave, icone in ICONE_TIPO_ITEM.items():
        if _normalizar(chave).lower() == alvo:
            return icone
    # Fuzzy match por palavras-chave se não bateu exato
    for chave, icone in ICONE_TIPO_ITEM.items():
        if _normalizar(chave).lower() in alvo:
            return icone
    return "📦"


ICONE_MATERIAL_PADRAO = "🧱"


def _icone_material(session, nome_material):
    mat = session.query(Material).filter_by(nome=nome_material).first()
    return mat.icone if (mat and mat.icone) else ICONE_MATERIAL_PADRAO


def _tier_do_player(session, player):
    local = None
    if player.local_atual:
        local = session.query(Local).filter_by(nome=player.local_atual).first()
    from db.models import Tier
    tiers = session.query(Tier).order_by(Tier.id).all()
    idx = max(0, min((player.tier_mais_alto_alcancado or 1) - 1, len(tiers) - 1))
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


# ---------- Menu principal de Comércio ----------

async def menu_comercio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    vagas_ocupadas = slots_mochila_ocupados(session, player) if player else 0
    max_vagas = player.slots_mochila_max or 20 if player else 20
    ouro = player.ouro or 0 if player else 0
    tier_nome = _tier_do_player(session, player) if player else "Sucata Enferrujada"
    ferreiro = _ferreiro_da_cidade(session, tier_nome) if player else None
    nome_ferreiro = ferreiro.nome if ferreiro else "Comerciante Local"
    session.close()

    texto = (
        f"🏪 *Mercado & Forja — {tier_nome}*\n"
        f"👤 Responsável: *{nome_ferreiro}*\n\n"
        f"💰 Seu Ouro: *{ouro}* 💰\n"
        f"🎒 Mochila: *{vagas_ocupadas}/{max_vagas}* vagas ocupadas\n\n"
        "Selecione uma ala do entreposto:"
    )

    botoes = [
        [InlineKeyboardButton("⚔️ Comprar Armas", callback_data="loja_comprar_arma"),
         InlineKeyboardButton("🛡️ Comprar Armaduras", callback_data="loja_comprar_armadura")],
        [InlineKeyboardButton("🧪 Poções e Antídotos", callback_data="loja_pocoes"),
         InlineKeyboardButton("🎓 Treinador", callback_data="menu_treinador")],
        [InlineKeyboardButton("💰 Balcão de Venda", callback_data="loja_vender"),
         InlineKeyboardButton("🔨 Forja & Artesanato", callback_data="loja_crafting")],
        [InlineKeyboardButton("🏥 Curandeiro & Templo", callback_data="menu_curandeiro")],
        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")],
    ]
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


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
    vagas_ocupadas = slots_mochila_ocupados(session, player)
    max_vagas = player.slots_mochila_max or 20

    icone = ICONE_CATEGORIA[categoria]

    # agrupa por Tipo/Slot
    por_tipo = {}
    for item in itens:
        chave = item.tipo if categoria == "arma" else item.slot
        por_tipo.setdefault(chave, []).append(item)

    if not tipo_filtro:
        texto = (
            f"{icone} *{nome_vendedor} — Vitrine de {categoria.capitalize()}s*\n"
            f"🏔️ Tier: _{tier_nome}_\n"
            f"💰 Seu Ouro: *{player.ouro or 0}* 💰  ·  🎒 Vagas: *{vagas_ocupadas}/{max_vagas}*\n\n"
            "Escolha uma categoria de equipamento:"
        )
        botoes = []
        for tipo, lista in sorted(por_tipo.items()):
            icone_tipo = _icone_tipo(tipo)
            botoes.append([InlineKeyboardButton(
                f"{icone_tipo} {tipo} ({len(lista)} modelos)",
                callback_data=f"loja_comprar_{categoria}_{tipo}",
            )])
        botoes.append([InlineKeyboardButton("⬅️ Voltar ao Comércio", callback_data="menu_comercio")])
        session.close()
        await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))
        return

    lista_tipo = por_tipo.get(tipo_filtro, [])
    icone_tipo = _icone_tipo(tipo_filtro)
    texto = (
        f"{icone} *{nome_vendedor} — {icone_tipo} {tipo_filtro}*\n"
        f"💰 Ouro: *{player.ouro or 0}* 💰  ·  🎒 Vagas: *{vagas_ocupadas}/{max_vagas}*\n"
    )
    if vagas_ocupadas >= max_vagas:
        texto += "\n⚠️ *Sua mochila está cheia! Libere espaço antes de comprar novos itens.*\n"

    botoes = []
    linha_botoes = []

    for idx, item in enumerate(lista_tipo, start=1):
        if categoria == "arma":
            stat_txt = f"⚔️ Dano: *{item.dano_comum}*"
        else:
            stat_txt = f"🛡️ Defesa: *{item.defesa_comum}*"

        preco_item = calcular_preco_compra_item(player, item, categoria)
        texto += f"\n*{idx}.* {icone_tipo} *{item.variacao}*\n"
        texto += f"   {stat_txt}  |  💰 *{preco_item}* Ouro\n"
        if item.efeito_especial:
            if getattr(item, "efeito_chance_pct", 0) > 0:
                val_txt = f" ({int(item.efeito_valor)} turnos)" if getattr(item, "efeito_valor", 0) > 0 and "turno" not in item.efeito_especial.lower() else ""
                texto += f"   ✨ *{int(item.efeito_chance_pct)}% de chance:* {item.efeito_especial}{val_txt}\n"
            else:
                texto += f"   ↳ ✨ _{item.efeito_especial}_\n"

        pode_comprar = (player.ouro or 0) >= preco_item and vagas_ocupadas < max_vagas
        label_btn = f"{idx}. Comprar ({preco_item}💰)" if len(lista_tipo) <= 4 else f"{idx} ({preco_item}💰)"

        if len(lista_tipo) <= 4:
            botoes.append([InlineKeyboardButton(
                f"{'✅' if pode_comprar else '🔒'} {label_btn}",
                callback_data=f"loja_comprarid_{categoria}_{item.id}",
            )])
        else:
            linha_botoes.append(InlineKeyboardButton(
                f"{idx} ({preco_item}💰)",
                callback_data=f"loja_comprarid_{categoria}_{item.id}",
            ))
            if len(linha_botoes) == 3:
                botoes.append(linha_botoes)
                linha_botoes = []

    if linha_botoes:
        botoes.append(linha_botoes)

    botoes.append([InlineKeyboardButton("⬅️ Voltar aos Tipos", callback_data=f"loja_comprar_{categoria}")])
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
        await query.answer(f"✅ Compra realizada com sucesso: {inv.nome_item}!", show_alert=True)
        from db.models import Arma, Armadura
        Modelo = Arma if categoria == "arma" else Armadura
        item_real = session.query(Modelo).filter_by(id=int(item_id)).first()
        if item_real:
            tipo_item_comprado = item_real.tipo if categoria == "arma" else item_real.slot
    except ErroEconomia as e:
        await query.answer(f"❌ {e}", show_alert=True)
    session.close()

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

    itens = (
        session.query(PlayerInventario)
        .filter(
            PlayerInventario.player_id == player.id,
            PlayerInventario.tipo_item.in_(["arma", "armadura", "acessorio", "arma_armadura_forjada"]),
            PlayerInventario.equipado == False,  # noqa: E712
        )
        .all()
    )

    texto = (
        "💰 *Balcão de Penhores & Venda*\n"
        f"💰 Seu Ouro: *{player.ouro or 0}* 💰\n\n"
        "Itens desequipados podem ser vendidos aqui por *40% do valor de vitrine*.\n"
        "_Itens equipados estão protegidos no seu corpo e não aparecem aqui._\n\n"
    )

    botoes = []
    total_estimado = 0

    if not itens:
        texto += "📭 Sua mochila não possui nenhum equipamento desequipado para venda."
    else:
        for idx, inv in enumerate(itens[:15], start=1):
            preco = 0
            icone_item = "📦"
            if inv.tipo_item == "arma":
                ref = session.query(Arma).filter_by(id=inv.item_ref_id).first()
                preco = ref.preco_venda_mercador if (ref and ref.preco_venda_mercador) else (int(round(ref.preco_compra * 0.4)) if ref else 0)
                icone_item = _icone_tipo(ref.tipo if ref else "Arma")
            elif inv.tipo_item == "armadura":
                ref = session.query(Armadura).filter_by(id=inv.item_ref_id).first()
                preco = ref.preco_venda_mercador if (ref and ref.preco_venda_mercador) else (int(round(ref.preco_compra * 0.4)) if ref else 0)
                icone_item = _icone_tipo(ref.slot if ref else "Armadura")
            elif inv.tipo_item == "acessorio":
                receita = session.query(Receita).filter_by(id=inv.item_ref_id).first()
                preco = int(round((receita.custo_base_ouro or 25) * 0.4)) if receita else 10
                icone_item = "💍"

            qtd = inv.quantidade or 1
            total_estimado += preco * qtd
            texto += f"*{idx}.* {icone_item} *{inv.nome_item}* x{qtd} — 💰 *{preco}* Ouro cada\n"
            botoes.append([InlineKeyboardButton(
                f"Vender {inv.nome_item} (+{preco}💰)", callback_data=f"loja_venderid_{inv.id}",
            )])

        botoes.insert(0, [InlineKeyboardButton(f"🧹 Vender Tudo (+{total_estimado} 💰)", callback_data="loja_vender_tudo")])

    botoes.append([InlineKeyboardButton("⬅️ Voltar ao Comércio", callback_data="menu_comercio")])
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
        await query.answer(f"✅ Item vendido com sucesso por +{preco} 💰 Ouro!", show_alert=True)
    except ErroEconomia as e:
        await query.answer(f"❌ {e}", show_alert=True)
    session.close()
    await listar_venda(update, context)


async def vender_tudo_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    total_ouro, total_itens = vender_tudo(session, player)
    session.close()
    if total_itens > 0:
        await query.answer(f"🧹 Sucesso! {total_itens} itens vendidos por +{total_ouro} 💰 Ouro!", show_alert=True)
    else:
        await query.answer("Nenhum equipamento desequipado para vender.", show_alert=True)
    await listar_venda(update, context)


# ---------- Crafting (Forja) ----------

SLOTS_ARMADURAS = ("Peitoral", "Escudo", "Elmo", "Luvas", "Bota", "Calça", "Calca", "Manopla")


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
        n_armas = sum(1 for r in todas_receitas if r.categoria == "Arma/Armadura" and r.tipo_slot not in SLOTS_ARMADURAS)
        n_armaduras = sum(1 for r in todas_receitas if r.categoria == "Arma/Armadura" and r.tipo_slot in SLOTS_ARMADURAS)
        n_acessorios = sum(1 for r in todas_receitas if r.categoria == "Acessório")
        n_ferramentas = sum(1 for r in todas_receitas if r.categoria == "Ferramenta de Coleta")
        n_comida = sum(1 for r in todas_receitas if r.categoria == "Comida/Bebida")
        session.close()

        botoes = [
            [InlineKeyboardButton(f"⚔️ Forja de Armas ({n_armas})", callback_data="loja_crafting_armas"),
             InlineKeyboardButton(f"🛡️ Forja de Armaduras ({n_armaduras})", callback_data="loja_crafting_armaduras")],
            [InlineKeyboardButton(f"💍 Acessórios ({n_acessorios})", callback_data="loja_crafting_acessorios"),
             InlineKeyboardButton(f"🛠️ Ferramentas ({n_ferramentas})", callback_data="loja_crafting_ferramentas")],
        ]
        if n_comida > 0:
            botoes.append([InlineKeyboardButton(f"🍖 Culinária & Alquimia ({n_comida})", callback_data="loja_crafting_comida")])
        botoes.append([InlineKeyboardButton("⬅️ Voltar ao Comércio", callback_data="menu_comercio")])
        await query.edit_message_text(
            f"🔨 *Forja & Artesanato Regional — {tier_nome}*\n\n"
            f"💰 Seu Ouro: *{player.ouro or 0}* 💰\n\n"
            "Economize recursos forjando seu próprio equipamento com materiais coletados!\n"
            "Escolha a categoria de manufatura:",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes),
        )
        return

    if categoria_filtro == "acessorios":
        receitas = [r for r in todas_receitas if r.categoria == "Acessório"]
        titulo_ala = "💍 Artesanato de Acessórios"
    elif categoria_filtro == "ferramentas":
        receitas = [r for r in todas_receitas if r.categoria == "Ferramenta de Coleta"]
        titulo_ala = "🛠️ Ferramentas de Coleta"
    elif categoria_filtro == "comida":
        receitas = [r for r in todas_receitas if r.categoria == "Comida/Bebida"]
        titulo_ala = "🍖 Culinária & Alquimia"
    elif categoria_filtro == "armaduras":
        receitas = [r for r in todas_receitas if r.categoria == "Arma/Armadura" and r.tipo_slot in SLOTS_ARMADURAS]
        titulo_ala = "🛡️ Forja de Armaduras"
    else:
        receitas = [r for r in todas_receitas if r.categoria == "Arma/Armadura" and r.tipo_slot not in SLOTS_ARMADURAS]
        titulo_ala = "⚔️ Forja de Armas"

    texto = f"🔨 *{titulo_ala} — {tier_nome}*\n💰 Seu Ouro: *{player.ouro or 0}* 💰\n"
    botoes = []

    for r in receitas[:15]:
        desbloqueada = receita_desbloqueada(session, player, r)
        pode, motivo, necessarios = verificar_forja(session, player, r.id)

        item_real = None
        if r.categoria == "Arma/Armadura":
            eh_armadura = r.tipo_slot in SLOTS_ARMADURAS
            if eh_armadura:
                candidatos = session.query(Armadura).filter_by(tier=tier_nome).order_by(Armadura.id).all()
                item_real = next((a for a in candidatos if _normalizar(a.slot) == _normalizar(r.tipo_slot)), None)
            else:
                candidatos = session.query(Arma).filter_by(tier=tier_nome).order_by(Arma.id).all()
                item_real = next((a for a in candidatos if _normalizar(a.tipo) == _normalizar(r.tipo_slot)), None)

        nome_exibido = item_real.variacao if item_real else r.tipo_slot
        icone_tipo_item = _icone_tipo(r.tipo_slot)

        marca = "🔓" if desbloqueada else "🔒"
        texto += f"\n➖➖➖➖➖➖➖➖➖➖\n{marca} {icone_tipo_item} *{nome_exibido}*\n"

        if item_real:
            if hasattr(item_real, "dano_comum") and item_real.dano_comum:
                texto += f"   ⚔️ Dano: *{item_real.dano_comum}*\n"
            elif hasattr(item_real, "defesa_comum") and item_real.defesa_comum:
                texto += f"   🛡️ Defesa: *{item_real.defesa_comum}*\n"

        # Comparativo com preço de vitrine
        custo_forja = r.custo_base_ouro or 0
        if item_real and item_real.preco_compra:
            vitrine = item_real.preco_compra
            economia = max(0, vitrine - custo_forja)
            texto += f"   💰 Custo: *{custo_forja}* 💰  _(Vitrine: {vitrine} 💰 — Economia: +{economia} 💰)_\n"
        else:
            texto += f"   💰 Custo: *{custo_forja}* 💰\n"

        if not desbloqueada:
            preco_diag = calcular_preco_diagrama(r)
            texto += f"   📜 *Diagrama Bloqueado!* Adquira a técnica por *{preco_diag}* 💰.\n"
            pode_comprar_diag = (player.ouro or 0) >= preco_diag
            botoes.append([InlineKeyboardButton(
                f"{'📜' if pode_comprar_diag else '🔒'} Comprar Diagrama ({preco_diag} 💰)",
                callback_data=f"loja_comp_diag_{r.id}",
            )])
        else:
            # Mostra contadores visuais de materiais
            materiais_linhas = []
            for nome_mat, qtd_nec in obter_materiais_receita(r):
                icone_mat = _icone_material(session, nome_mat)
                inv_mat = (
                    session.query(PlayerInventario)
                    .filter_by(player_id=player.id, tipo_item="material", nome_item=nome_mat)
                    .first()
                )
                qtd_tem = inv_mat.quantidade if inv_mat else 0
                check = "✅" if qtd_tem >= qtd_nec else "❌"
                materiais_linhas.append(f"   {icone_mat} {nome_mat}: *{qtd_tem}/{qtd_nec}* {check}")

            if materiais_linhas:
                texto += "   *Materiais Necessários:*\n" + "\n".join(materiais_linhas) + "\n"

            if r.efeito and r.categoria in ("Acessório", "Ferramenta de Coleta", "Comida/Bebida"):
                texto += f"   ↳ ✨ _{r.efeito}_\n"
            elif item_real and item_real.lore:
                texto += f"   _{item_real.lore}_\n"

            btn_label = f"🔨 Forjar {nome_exibido}" if pode else f"🔒 Forjar {nome_exibido}"
            botoes.append([InlineKeyboardButton(btn_label, callback_data=f"loja_forjar_{r.id}")])

    botoes.append([InlineKeyboardButton("⬅️ Voltar às Categorias", callback_data="loja_crafting")])
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def confirmar_forja(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    receita_id = int(query.data.split("_")[-1])
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    categoria_receita = None
    slot_receita = None
    try:
        receita = session.query(Receita).filter_by(id=receita_id).first()
        if receita:
            categoria_receita = receita.categoria
            slot_receita = receita.tipo_slot
        item = forjar_item(session, player, receita_id)
        await query.answer(f"✅ Forjado com perfeição: {item.nome_item}!", show_alert=True)
    except ErroEconomia as e:
        await query.answer(f"❌ {e}", show_alert=True)
    session.close()

    if categoria_receita == "Acessório":
        query.data = "loja_crafting_acessorios"
    elif slot_receita in SLOTS_ARMADURAS:
        query.data = "loja_crafting_armaduras"
    else:
        query.data = "loja_crafting_armas"
    await menu_crafting(update, context)


async def confirmar_comprar_diagrama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    receita_id = int(query.data.split("_")[-1])
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    categoria_receita = None
    slot_receita = None
    try:
        receita, preco = comprar_diagrama(session, player, receita_id)
        categoria_receita = receita.categoria
        slot_receita = receita.tipo_slot
        await query.answer(f"✅ Diagrama de {receita.tipo_slot} desbloqueado por {preco} 💰!", show_alert=True)
    except ErroEconomia as e:
        await query.answer(f"❌ {e}", show_alert=True)
    session.close()

    if categoria_receita == "Acessório":
        query.data = "loja_crafting_acessorios"
    elif slot_receita in SLOTS_ARMADURAS:
        query.data = "loja_crafting_armaduras"
    else:
        query.data = "loja_crafting_armas"
    await menu_crafting(update, context)


# ---------- Treinador de Habilidades ----------

async def menu_treinador(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    if not player:
        session.close()
        return

    from game.nivel import calcular_upgrade_rank
    from db.models import HabilidadeAtiva

    res = calcular_upgrade_rank(session, player)
    rank_atual = player.habilidade_ativa_nivel or 1

    if res.get("motivo") == "rank_maximo":
        session.close()
        texto = (
            "🎓 *Treinador de Habilidades*\n\n"
            "Sua habilidade já atingiu o domínio máximo (Rank 5)."
        )
        botoes = [[InlineKeyboardButton("⬅️ Voltar ao Comércio", callback_data="menu_comercio")]]
        await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))
        return

    hab = res.get("habilidade")
    if not hab and player.classe_id:
        hab = session.query(HabilidadeAtiva).filter_by(classe_id=player.classe_id).first()

    hab_nome = hab.habilidade_nome if hab else "Habilidade Ativa"
    proximo_rank = res.get("proximo_rank")
    nivel_necessario = res.get("nivel_necessario")
    custo = res.get("custo")
    ouro_atual = player.ouro or 0
    pode_upar = res.get("pode_upar", False)

    texto = (
        f"🎓 *Treinador de Habilidades — {hab_nome}*\n\n"
        f"🎓 Rank atual: *{rank_atual}/5*\n"
        f"Próximo Rank: *{proximo_rank}*\n"
        f"📈 Nível necessário: *{nivel_necessario}* (você: {player.nivel})\n"
        f"💰 Custo: *{custo}* Ouro (você tem: {ouro_atual})\n"
    )

    if pode_upar:
        botoes = [
            [InlineKeyboardButton(f"✅ Evoluir para Rank {proximo_rank}", callback_data="treinador_upar")],
            [InlineKeyboardButton("⬅️ Voltar ao Comércio", callback_data="menu_comercio")],
        ]
    else:
        motivo = res.get("motivo")
        if motivo == "nivel_insuficiente":
            texto += f"\n⚠️ *Nível insuficiente:* você precisa atingir o Nível {nivel_necessario} (você é Nv {player.nivel}).\n"
        elif motivo == "ouro_insuficiente":
            texto += f"\n⚠️ *Ouro insuficiente:* você precisa de {custo} Ouro (você tem {ouro_atual} Ouro).\n"
        elif motivo == "habilidade_nao_encontrada":
            texto += "\n⚠️ *Habilidade não encontrada para a sua classe.*\n"
        botoes = [
            [InlineKeyboardButton("⬅️ Voltar ao Comércio", callback_data="menu_comercio")],
        ]

    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def confirmar_upgrade_rank(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    if not player:
        await query.answer("Jogador não encontrado.", show_alert=True)
        session.close()
        return

    from game.nivel import calcular_upgrade_rank, aplicar_upgrade_rank
    res = calcular_upgrade_rank(session, player)
    if not res.get("pode_upar"):
        await query.answer(f"Não foi possível evoluir: {res.get('motivo')}", show_alert=True)
        session.close()
        await menu_treinador(update, context)
        return

    try:
        resultado = aplicar_upgrade_rank(session, player)
        session.commit()
    except Exception as e:
        session.rollback()
        session.close()
        await query.answer(f"Erro ao aprimorar: {e}", show_alert=True)
        await menu_treinador(update, context)
        return

    hab = resultado.get("habilidade")
    novo_rank = player.habilidade_ativa_nivel
    dano_pct = getattr(hab, f"dano_pct_rank{novo_rank}", 1.0)
    ef_sec = getattr(hab, f"efeito_secundario_rank{novo_rank}", 0.0)
    ef_tipo = getattr(hab, "efeito_secundario_tipo", "")
    nome_hab = hab.habilidade_nome if hab else "Habilidade"

    session.close()
    await query.answer("🎉 Habilidade aprimorada com sucesso!", show_alert=True)

    texto = (
        f"🎉 *Habilidade Aprimorada com Sucesso!*\n\n"
        f"⚡ *{nome_hab}* alcançou o *Rank {novo_rank}*!\n\n"
        f"💥 Multiplicador de Dano: *{dano_pct:.2f}x*\n"
        f"✨ Efeito Secundário ({ef_tipo}): *{ef_sec}*\n"
    )
    botoes = [
        [InlineKeyboardButton("⬅️ Voltar ao Treinador", callback_data="menu_treinador")],
        [InlineKeyboardButton("🏛️ Voltar ao Comércio", callback_data="menu_comercio")],
    ]
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


# ---------- Loja de Poções ----------

async def listar_pocoes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    if not player:
        session.close()
        return

    from db.models import Consumivel
    tier_nome = _tier_do_player(session, player)
    itens = session.query(Consumivel).filter_by(tier=tier_nome).all()
    vagas_ocupadas = slots_mochila_ocupados(session, player)
    max_vagas = player.slots_mochila_max or 20
    ouro = player.ouro or 0

    texto = (
        f"🧪 *Empório Alquímico — {tier_nome}*\n"
        f"💰 Seu Ouro: *{ouro}* 💰  ·  🎒 Mochila: *{vagas_ocupadas}/{max_vagas}* vagas ocupadas\n\n"
        "Selecione uma poção para comprar:\n"
    )

    botoes = []
    for item in itens:
        icone = "❤️" if item.tipo == "cura" else ("🔷" if item.tipo == "mana" else "🧪")
        texto += f"\n{icone} *{item.nome}*\n   ↳ _{item.efeito_descricao}_  |  💰 *{item.preco_compra}* Ouro\n"

        pode = ouro >= (item.preco_compra or 0) and vagas_ocupadas < max_vagas
        label = f"{'✅' if pode else '🔒'} Comprar {item.nome} ({item.preco_compra}💰)"
        botoes.append([InlineKeyboardButton(label, callback_data=f"pocao_comprar_{item.id}")])

    botoes.append([InlineKeyboardButton("⬅️ Voltar ao Comércio", callback_data="menu_comercio")])
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def confirmar_compra_pocao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    item_id = int(query.data.replace("pocao_comprar_", ""))

    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    if not player:
        await query.answer("Jogador não encontrado.", show_alert=True)
        session.close()
        return

    from db.models import Consumivel
    consumivel = session.query(Consumivel).filter_by(id=item_id).first()
    if not consumivel:
        await query.answer("Poção não encontrada.", show_alert=True)
        session.close()
        return

    preco = consumivel.preco_compra or 0
    if (player.ouro or 0) < preco:
        await query.answer("Ouro insuficiente para comprar esta poção.", show_alert=True)
        session.close()
        return

    vagas_ocupadas = slots_mochila_ocupados(session, player)
    max_vagas = player.slots_mochila_max or 20

    existente = (
        session.query(PlayerInventario)
        .filter_by(player_id=player.id, tipo_item="consumivel", nome_item=consumivel.nome)
        .first()
    )

    if not existente and vagas_ocupadas >= max_vagas:
        await query.answer("Mochila cheia! Libere espaço antes de comprar.", show_alert=True)
        session.close()
        return

    player.ouro -= preco
    if existente:
        existente.quantidade = (existente.quantidade or 1) + 1
    else:
        session.add(PlayerInventario(
            player_id=player.id,
            tipo_item="consumivel",
            item_ref_id=consumivel.id,
            nome_item=consumivel.nome,
            quantidade=1,
            equipado=False,
            danificado=False,
        ))

    session.commit()
    session.close()
    await query.answer(f"✅ Comprou {consumivel.nome} por {preco} Ouro!", show_alert=True)
    await listar_pocoes(update, context)


# ============================================================
# CURANDEIRO & TEMPLO DA CIDADE (Item 11.6)
# ============================================================

def _calcular_custo_servico_curandeiro(player, custo_base: int) -> int:
    """Aplica modificador de preço ao curandeiro (Mutação 6: -5% desconto)."""
    custo = float(custo_base)
    from game.combat import _obter_mutacoes_player
    mutacoes = _obter_mutacoes_player(player)
    if any(getattr(m, "mutacao_id", 0) == 6 or "Voz Dupla" in (getattr(m, "nome", "") or "") for m in mutacoes):
        custo *= 0.95
    return max(1, round(custo))


async def menu_curandeiro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    session = get_session()
    user_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=user_id).first()
    if not player:
        session.close()
        return

    nome_local = player.local_atual or "Vale Cinza"
    if player.local_atual:
        loc = session.query(Local).filter_by(nome=player.local_atual).first()
        if loc and loc.nome:
            nome_local = loc.nome

    texto = f"🏥 *Curandeiro de {nome_local}*\n\n"
    texto += "O santuário ressoa com hinos sagrados e o calor de incensos aromáticos. Aqui você pode fechar feridas de guerra e purificar sua carne da infecção cósmica.\n\n"
    texto += f"❤️ *HP:* {player.hp_atual}/{player.hp_max}\n"
    texto += f"💰 *Seu Ouro:* {player.ouro or 0}\n"

    custo_cura = _calcular_custo_servico_curandeiro(player, 20)
    custo_tratar = _calcular_custo_servico_curandeiro(player, 10)

    botoes = []
    # 1. Curar HP (padrão) — {custo_cura} ouro
    botoes.append([InlineKeyboardButton(f"💊 Curar HP (padrão) — {custo_cura} ouro", callback_data="curandeiro_curar_hp")])

    # 2. Tratar Ferimento — {custo_tratar} ouro (apenas se houver debuff ativo curável)
    debuff = getattr(player, "debuff_ativo", None)
    if debuff and debuff != "Marca do Medo":
        botoes.append([InlineKeyboardButton(f"🩹 Tratar Ferimento ({debuff}) — {custo_tratar} ouro", callback_data="curandeiro_tratar_ferimento")])

    # 3. Purificação (-20 Corrupção) — {custo} ouro
    corr = getattr(player, "corrupcao", 0) or 0
    if corr > 0:
        from game.corrupcao import custo_purificacao
        custo_purif = custo_purificacao(corr)
        botoes.append([InlineKeyboardButton(f"✨ Purificação (-20 Corrupção) — {custo_purif} ouro", callback_data="curandeiro_purificar")])

    botoes.append([InlineKeyboardButton("🔙 Voltar ao Comércio", callback_data="menu_comercio")])

    markup = InlineKeyboardMarkup(botoes)
    session.close()
    if query:
        await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=markup)
    else:
        await update.message.reply_text(texto, parse_mode="Markdown", reply_markup=markup)


async def curar_hp_curandeiro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    user_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=user_id).first()
    if not player:
        session.close()
        return

    CUSTO_CURA = _calcular_custo_servico_curandeiro(player, 20)
    if (player.ouro or 0) < CUSTO_CURA:
        await query.answer(f"Ouro insuficiente! O curandeiro cobra {CUSTO_CURA} ouro.", show_alert=True)
        session.close()
        return

    if player.hp_atual >= player.hp_max:
        await query.answer("Você já está com a vida cheia!", show_alert=True)
        session.close()
        return

    from game.corrupcao import modificador_cura_corrupcao
    mod_cura = modificador_cura_corrupcao(player)
    if mod_cura <= 0.0:
        await query.answer("Sua carne está tão corrompida que as bênçãos sagradas não surtem efeito!", show_alert=True)
        session.close()
        return

    # Regra oficial da V1.0 (BUG-002 documentado): A cura do curandeiro restaura proporcionalmente o HP que falta,
    # multiplicada pelo modificador de cura da corrupção/mutações (mod_cura).
    hp_faltando = player.hp_max - player.hp_atual
    hp_recuperado = max(1, int(hp_faltando * mod_cura))
    player.hp_atual = min(player.hp_max, player.hp_atual + hp_recuperado)
    player.ouro -= CUSTO_CURA
    session.commit()
    session.close()

    await query.answer(f"✅ Curado em +{hp_recuperado} HP por {CUSTO_CURA} ouro!", show_alert=True)
    await menu_curandeiro(update, context)


async def tratar_ferimento_curandeiro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    user_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=user_id).first()
    if not player:
        session.close()
        return

    CUSTO_TRATAR = _calcular_custo_servico_curandeiro(player, 10)
    if (player.ouro or 0) < CUSTO_TRATAR:
        await query.answer(f"Ouro insuficiente! O tratamento custa {CUSTO_TRATAR} ouro.", show_alert=True)
        session.close()
        return

    debuff = getattr(player, "debuff_ativo", None)
    if not debuff or debuff == "Marca do Medo":
        await query.answer("Você não possui ferimentos físicos para tratar.", show_alert=True)
        session.close()
        return

    from game.atributos import calcular_hp_max, calcular_vigor_max
    debuff_removido = debuff
    player.debuff_ativo = None
    player.ouro -= CUSTO_TRATAR

    # Recalcula atributos afetados por debuff (Ferida Profunda -> HP máx, Fadiga Persistente -> Vigor máx) - BUG-001 corrigido
    player.hp_max = calcular_hp_max(player)
    player.vig_max = calcular_vigor_max(player)
    player.hp_atual = min(player.hp_max, player.hp_atual or player.hp_max)
    player.vig_atual = min(player.vig_max, player.vig_atual or player.vig_max)

    session.commit()
    session.close()

    await query.answer(f"✅ {debuff_removido} foi completamente curado por {CUSTO_TRATAR} ouro!", show_alert=True)
    await menu_curandeiro(update, context)


async def purificar_curandeiro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    user_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=user_id).first()
    if not player:
        session.close()
        return

    from game.corrupcao import purificar_corrupcao
    sucesso, msg, custo = purificar_corrupcao(session, player, 20)
    await query.answer(msg, show_alert=True)
    session.close()
    await menu_curandeiro(update, context)

