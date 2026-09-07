"""
Fase 4 — Painel do Personagem em 5 Telas Especializadas:
[ 👤 Perfil ] [ 🛡️ Equip ] [ 🎒 Mochila ] [ 🧱 Materiais ] [ 📖 Grimório ]

Implementação direta conforme as regras oficiais da planilha:
- Perfil: Atributos base + modificadores, barras gráficas, Defesa total consolidada,
  Corrupção e Mutações ativas, distribuição rápida de pontos de atributo.
- Equipamentos: Paperdoll visual dos 8 slots corporais + Arma, detecção de empunhadura
  dupla versátil (+20%/+25% dano) com mão secundária livre, desequipar por peça.
- Mochila: Armas/armaduras sobressalentes e consumíveis, limite de 20 vagas,
  ações de equipar, usar e descartar.
- Materiais: Itens de coleta e crafting com capacidade ilimitada, ícones e biomas de origem.
- Grimório: Magias desbloqueadas por Grau e Elemento com custos, dano e instrução de combate.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.connection import get_session
from db.models import (
    Player, PlayerInventario, PlayerMutacao, Classe, CurvaMestra,
    Arma, Armadura, Material, Magia, Receita, HabilidadeAtiva,
)
from game.atributos import calcular_defesa_total
from game.combat import calcular_modificador_empunhadura
from game.corrupcao import estagio_corrupcao, bonus_defesa_corrupcao
from game.economia import slots_mochila_ocupados
from handlers.comercio import _icone_tipo

ICONE_ELEMENTO = {
    "Fogo": "🔥", "Gelo": "❄️", "Raio": "⚡", "Sombra": "🌑", "Luz": "✨", "Arcano": "🔮",
}
CUSTO_POR_GRAU = {"Basico": 0.15, "Avancado": 0.4, "Mestre": 0.65}


def barra_grafica(atual: int, maximo: int, tamanho: int = 8, cheio: str = "🟩", vazio: str = "⬛") -> str:
    if not maximo or maximo <= 0:
        return vazio * tamanho
    proporcao = max(0.0, min(1.0, atual / maximo))
    num_cheios = round(proporcao * tamanho)
    num_vazios = tamanho - num_cheios
    return (cheio * num_cheios) + (vazio * num_vazios)


def barra_navegacao_personagem(aba_ativa: str) -> list[list[InlineKeyboardButton]]:
    """Gera a barra de abas padronizada das 5 telas do personagem."""
    abas = [
        ("perfil", "👤 Perfil"),
        ("equip", "🛡️ Equip"),
        ("mochila", "🎒 Mochila"),
        ("materiais", "🧱 Materiais"),
        ("grimorio", "📖 Grimório"),
    ]
    linha1 = []
    linha2 = []
    for chave, rotulo in abas[:3]:
        texto_btn = f"• {rotulo} •" if chave == aba_ativa else rotulo
        linha1.append(InlineKeyboardButton(texto_btn, callback_data=f"painel_{chave}"))
    for chave, rotulo in abas[3:]:
        texto_btn = f"• {rotulo} •" if chave == aba_ativa else rotulo
        linha2.append(InlineKeyboardButton(texto_btn, callback_data=f"painel_{chave}"))
    return [linha1, linha2]


# ============================================================
# TELA 1: PERFIL (Atributos e Estatísticas)
# ============================================================

async def painel_perfil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    if not player:
        session.close()
        return

    classe = session.get(Classe, player.classe_id) if player.classe_id else None
    nome_classe = classe.nome if classe else "Aventureiro"

    curva = session.query(CurvaMestra).filter_by(nivel=player.nivel or 1).first()
    xp_prox = curva.xp_prox_nivel if curva else 20
    xp_atual = player.xp_atual or 0

    hp_max = player.hp_max or 24
    hp_atual = player.hp_atual if player.hp_atual is not None else hp_max
    vig_max = player.vig_max or 60
    vig_atual = player.vig_atual if player.vig_atual is not None else vig_max
    mana_max = player.mana_max or 0
    mana_atual = player.mana_atual if player.mana_atual is not None else mana_max

    defesa_total = calcular_defesa_total(player, session)

    arma_eq = (
        session.query(PlayerInventario)
        .filter_by(player_id=player.id, tipo_item="arma", equipado=True)
        .first()
    )
    dano_arma = 3
    nome_arma = "Desarmado"
    if arma_eq:
        arma_obj = session.get(Arma, arma_eq.item_ref_id)
        if arma_obj:
            dano_arma = arma_obj.dano_comum or 3
            nome_arma = arma_obj.variacao

    from game.ui_utils import esc_md
    nome_escapado = esc_md(player.nome_personagem or "Aventureiro")
    titulo_txt = f", o {esc_md(player.titulo_ativo)}" if getattr(player, "titulo_ativo", None) else ""
    nome_arma_esc = esc_md(nome_arma)
    texto = (
        f"👤 *Perfil do Personagem*\n"
        f"*{nome_escapado}{titulo_txt}* — {esc_md(nome_classe)}\n"
        f"🎖️ Nível *{player.nivel or 1}*  ·  🏔️ Tier *{player.tier_mais_alto_alcancado or 1}*  ·  💰 *{player.ouro or 0}* Ouro\n\n"
        f"❤️ HP: {hp_atual}/{hp_max}\n{barra_grafica(hp_atual, hp_max, 10, '🟥', '⬛')}\n"
        f"⚡ Vigor: {vig_atual}/{vig_max}\n{barra_grafica(vig_atual, vig_max, 10, '🟩', '⬛')}\n"
    )
    if mana_max > 0:
        texto += f"🔷 Mana: {mana_atual}/{mana_max}\n{barra_grafica(mana_atual, mana_max, 10, '🟦', '⬛')}\n"
    from game.atributos import calcular_critico_chance
    crit_chance = int(round(calcular_critico_chance(player=player, classe=classe)))
    chance_fuga_atual = int(round((0.40 + ((vig_atual / max(1, vig_max)) * 0.20)) * 100))

    texto += (
        "⚔️ *Estatísticas de Combate:*\n"
        f"🗡️ *Ataque Base:* *{dano_arma}* ({nome_arma_esc})\n"
        f"🛡️ *Defesa Total:* *{defesa_total}* (Armaduras & Escudo)\n"
        f"🎯 *Chance de Crítico:* *{crit_chance}%*\n"
        f"🏃 *Chance de Fuga:* *{chance_fuga_atual}%* (40%–60% via Vigor)\n\n"
    )

    from game.ui_utils import (
        formatar_bloco_maestria, formatar_bloco_corrupcao,
        formatar_bloco_mutacoes, formatar_bloco_debuff,
        formatar_bloco_titulo,
    )

    # 2. Maestria de Arma (Item 11.2)
    tipo_arma_maestria = arma_obj.tipo if (arma_eq and arma_obj) else "Espada"
    from db.models import PlayerProficiencia
    from game.proficiencia import nivel_e_progresso
    prof = session.query(PlayerProficiencia).filter_by(player_id=player.id, tipo_arma=tipo_arma_maestria).first()
    nv_prof, _, _ = nivel_e_progresso(prof.valor if prof else 0)
    texto += formatar_bloco_maestria(tipo_arma_maestria, nv_prof, nome_classe) + "\n\n"

    # 3. Título Ativo com bônus real (Item 11.8)
    texto += formatar_bloco_titulo(player.titulo_ativo, session) + "\n\n"

    # 4. Corrupção com bônus e botão (Item 11.1)
    corr = player.corrupcao or 0
    texto += formatar_bloco_corrupcao(corr) + "\n\n"

    # 5. Mutações Ativas (Item 11.1)
    mutacoes = session.query(PlayerMutacao).filter_by(player_id=player.id).all()
    if mutacoes:
        texto += formatar_bloco_mutacoes(mutacoes) + "\n\n"

    # 6. Status Debuff Ativo (Item 11.1 condicional)
    if player.debuff_ativo:
        texto += formatar_bloco_debuff(player.debuff_ativo) + "\n\n"

    botoes = barra_navegacao_personagem("perfil")

    if corr > 0:
        from game.corrupcao import custo_purificacao
        custo_purif = custo_purificacao(corr)
        botoes.insert(0, [InlineKeyboardButton(f"💰 Purificar (-20 pontos): {custo_purif} ouro", callback_data="purificar_ficha")])

    botoes.append([InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="menu_status")])
    session.close()

    markup = InlineKeyboardMarkup(botoes)
    if query:
        await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=markup)
    else:
        await update.message.reply_text(texto, parse_mode="Markdown", reply_markup=markup)


async def purificar_ficha_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    if not player:
        session.close()
        return
    from game.corrupcao import purificar_corrupcao
    sucesso, msg, _ = purificar_corrupcao(session, player, 20)
    await query.answer(msg, show_alert=True)
    session.close()
    await painel_perfil(update, context)


# ============================================================
# TELA 2: EQUIPAMENTOS (Paperdoll dos 8 Slots + Arma)
# ============================================================

SLOTS_ORDEM = [
    ("Arma", "⚔️ Mão Principal (Arma)"),
    ("Escudo", "🔰 Mão Secundária (Escudo)"),
    ("Elmo", "⛑️ Cabeça (Elmo)"),
    ("Peitoral", "🛡️ Tronco (Peitoral)"),
    ("Luvas", "🧤 Mãos (Luvas)"),
    ("Calca", "👖 Pernas (Calça)"),
    ("Bota", "👢 Pés (Bota)"),
    ("Amuleto", "📿 Acessório 1 (Amuleto)"),
    ("Anel", "💍 Acessório 2 (Anel)"),
]


async def painel_equipamentos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    if not player:
        session.close()
        return

    itens_equipados = (
        session.query(PlayerInventario)
        .filter_by(player_id=player.id, equipado=True)
        .all()
    )

    # Mapeia itens equipados por slot
    slot_map = {}
    arma_equipada = None
    for inv in itens_equipados:
        if inv.tipo_item == "arma":
            arma = session.query(Arma).filter_by(id=inv.item_ref_id).first() if inv.item_ref_id else None
            stat = f" — ⚔️ Dano {arma.dano_comum}" if arma else ""
            if arma and arma.efeito_especial:
                if getattr(arma, "efeito_chance_pct", 0) > 0:
                    val_t = f" ({int(arma.efeito_valor)} turnos)" if getattr(arma, "efeito_valor", 0) > 0 and "turno" not in arma.efeito_especial.lower() else ""
                    stat += f"\n   ✨ {int(arma.efeito_chance_pct)}% de chance: {arma.efeito_especial}{val_t}"
                else:
                    stat += f"\n   ✨ {arma.efeito_especial}"
            slot_map["Arma"] = (inv, arma, stat)
            arma_equipada = arma
        elif inv.tipo_item == "armadura":
            arm = session.query(Armadura).filter_by(id=inv.item_ref_id).first() if inv.item_ref_id else None
            slot_nome = arm.slot if arm else "Peitoral"
            stat = f" — 🛡️ Defesa {arm.defesa_comum}" if arm else ""
            slot_map[slot_nome] = (inv, arm, stat)
        elif inv.tipo_item == "acessorio":
            rec = session.query(Receita).filter_by(id=inv.item_ref_id).first() if inv.item_ref_id else None
            stat = f" — ✨ {rec.efeito}" if (rec and rec.efeito) else ""
            slot_nome = "Anel" if "anel" in (inv.nome_item or "").lower() else "Amuleto"
            slot_map[slot_nome] = (inv, rec, stat)

    defesa_total = calcular_defesa_total(player, session)

    texto = (
        "🛡️ *Equipamentos & Traje de Batalha*\n"
        f"Defesa Consolidada: *{defesa_total}* 🛡️\n\n"
        "*Paperdoll Corporal:*\n"
    )

    botoes_desequipar = []

    for chave_slot, rotulo in SLOTS_ORDEM:
        if chave_slot in slot_map:
            inv_item, ref_item, stat_txt = slot_map[chave_slot]
            texto += f"• {rotulo}: *{inv_item.nome_item}*{stat_txt}\n"
            botoes_desequipar.append([InlineKeyboardButton(
                f"❌ Desequipar {chave_slot}",
                callback_data=f"inv_desequipar_{inv_item.id}",
            )])
        else:
            # Slot livre: verifica empunhadura dupla versátil se for o Escudo
            if chave_slot == "Escudo":
                tipo_arma = arma_equipada.tipo if arma_equipada else ""
                mod_grip, _ = calcular_modificador_empunhadura(tipo_arma, slot_secundario_ocupado=False)
                if mod_grip == 1.25:
                    texto += f"• {rotulo}: _(vazio) — ⚔️ Empunhadura Dupla Ativa (+25% de dano!)_\n"
                elif mod_grip == 1.20:
                    texto += f"• {rotulo}: _(vazio) — ⚔️ Empunhadura Dupla Ativa (+20% de dano!)_\n"
                else:
                    texto += f"• {rotulo}: _(vazio)_\n"
            else:
                texto += f"• {rotulo}: _(vazio)_\n"

    if arma_equipada:
        from db.models import PlayerProficiencia, Classe
        from game.proficiencia import nivel_e_progresso
        from game.ui_utils import formatar_bloco_maestria
        cls_obj = session.get(Classe, player.classe_id) if player.classe_id else None
        cls_nm = cls_obj.nome if cls_obj else ""
        prof = session.query(PlayerProficiencia).filter_by(player_id=player.id, tipo_arma=arma_equipada.tipo).first()
        nv_prof, _, _ = nivel_e_progresso(prof.valor if prof else 0)
        texto += "\n" + formatar_bloco_maestria(arma_equipada.tipo, nv_prof, cls_nm)

    session.close()

    botoes = barra_navegacao_personagem("equip")
    if botoes_desequipar:
        botoes.extend(botoes_desequipar)
    botoes.append([InlineKeyboardButton("🎒 Abrir Mochila para Equipar", callback_data="painel_mochila")])
    botoes.append([InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="menu_status")])

    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


# ============================================================
# TELA 3: MOCHILA (Itens Sobressalentes e Consumíveis)
# ============================================================

async def painel_mochila(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    if not player:
        session.close()
        return

    itens_mochila = (
        session.query(PlayerInventario)
        .filter(
            PlayerInventario.player_id == player.id,
            PlayerInventario.tipo_item != "material",
            PlayerInventario.equipado == False,  # noqa: E712
        )
        .all()
    )

    vagas_ocupadas = slots_mochila_ocupados(session, player)
    max_vagas = player.slots_mochila_max or 20

    texto = (
        f"🎒 *Mochila do Viajante*\n"
        f"Capacidade: *{vagas_ocupadas}/{max_vagas}* vagas ocupadas\n\n"
    )

    botoes = barra_navegacao_personagem("mochila")

    if not itens_mochila:
        texto += "📭 Sua mochila está vazia de equipamentos sobressalentes e consumíveis.\n"
    else:
        for idx, item in enumerate(itens_mochila, start=1):
            stat_txt = ""
            icone = "📦"
            if item.tipo_item == "arma":
                arma = session.query(Arma).filter_by(id=item.item_ref_id).first() if item.item_ref_id else None
                stat_txt = f" — ⚔️ Dano: {arma.dano_comum}" if arma else ""
                icone = _icone_tipo(arma.tipo if arma else "Arma")
                if arma and arma.efeito_especial:
                    if getattr(arma, "efeito_chance_pct", 0) > 0:
                        val_t = f" ({int(arma.efeito_valor)} turnos)" if getattr(arma, "efeito_valor", 0) > 0 and "turno" not in arma.efeito_especial.lower() else ""
                        stat_txt += f"\n   ✨ {int(arma.efeito_chance_pct)}% de chance: {arma.efeito_especial}{val_t}"
                    else:
                        stat_txt += f"\n   ✨ {arma.efeito_especial}"
            elif item.tipo_item == "armadura":
                arm = session.query(Armadura).filter_by(id=item.item_ref_id).first() if item.item_ref_id else None
                stat_txt = f" — 🛡️ Defesa: {arm.defesa_comum}" if arm else ""
                icone = _icone_tipo(arm.slot if arm else "Armadura")
            elif item.tipo_item == "acessorio":
                rec = session.query(Receita).filter_by(id=item.item_ref_id).first() if item.item_ref_id else None
                stat_txt = f" — ✨ {rec.efeito}" if (rec and rec.efeito) else ""
                icone = "💍"
            elif item.tipo_item in ("consumivel", "ferramenta"):
                icone = "🧪" if item.tipo_item == "consumivel" else "🔨"

            texto += f"*{idx}.* {icone} *{item.nome_item}* x{item.quantidade or 1}{stat_txt}\n"

            linha_acao = []
            if item.tipo_item in ("arma", "armadura", "acessorio"):
                linha_acao.append(InlineKeyboardButton(f"⚡ Equipar {item.nome_item}", callback_data=f"inv_equipar_{item.id}"))
            elif item.tipo_item == "consumivel":
                linha_acao.append(InlineKeyboardButton(f"🧪 Usar {item.nome_item}", callback_data=f"inv_usar_{item.id}"))

            linha_acao.append(InlineKeyboardButton("🗑️ Descartar", callback_data=f"inv_descartar_{item.id}"))
            botoes.append(linha_acao)

    session.close()
    botoes.append([InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="menu_status")])
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


# ============================================================
# TELA 4: BOLSA DE MATERIAIS (Crafting e Coleta)
# ============================================================

async def painel_materiais(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    if not player:
        session.close()
        return

    materiais = (
        session.query(PlayerInventario)
        .filter_by(player_id=player.id, tipo_item="material")
        .all()
    )

    texto = (
        "🧱 *Bolsa de Materiais & Recursos*\n"
        "Capacidade: *Ilimitada ♾️* _(materiais de coleta não ocupam vagas na mochila)_\n\n"
    )

    from game.combat import _obter_mutacoes_player
    tem_mut_18 = any(getattr(m, "mutacao_id", 0) == 18 or "Digestão de Minérios" in (getattr(m, "nome", "") or "") for m in _obter_mutacoes_player(player))

    botoes_consumir = []
    if not materiais:
        texto += "📭 Sua bolsa de materiais está vazia. Explore regiões e derrote monstros para obter recursos brutos."
    else:
        if tem_mut_18:
            texto += "🧬 *Digestão de Minérios:* Sua fisiologia aberrante permite triturar e digerir minerais para fechar ferimentos (+10 HP por material comum)!\n\n"

        for item in materiais:
            mat = session.query(Material).filter_by(nome=item.nome_item).first()
            icone = mat.icone if (mat and mat.icone) else "🧱"
            bioma = mat.bioma if mat else "Mundo"
            cat = mat.categoria if mat else "Recurso"
            uso = mat.uso_principal if mat else "Forja & Alquimia"
            texto += f"{icone} *{item.nome_item}* x{item.quantidade}\n   📍 Origem: _{bioma}_ | {cat}\n   💡 Uso: _{uso}_\n\n"
            if tem_mut_18 and item.quantidade > 0:
                botoes_consumir.append([InlineKeyboardButton(f"🩺 Consumir {item.nome_item} (+10 HP)", callback_data=f"consumir_mat_{item.id}")])

    session.close()
    botoes = barra_navegacao_personagem("materiais")
    for b in botoes_consumir:
        botoes.insert(-1, b)
    botoes.append([InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="menu_status")])
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def consumir_material_mutacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mutação 18 (Digestão de Minérios): Consome 1 material comum para regenerar 10 HP."""
    query = update.callback_query
    inv_id = int(query.data.split("_")[-1])

    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    if not player:
        session.close()
        return

    from game.combat import _obter_mutacoes_player
    tem_mut_18 = any(getattr(m, "mutacao_id", 0) == 18 or "Digestão de Minérios" in (getattr(m, "nome", "") or "") for m in _obter_mutacoes_player(player))
    if not tem_mut_18:
        session.close()
        await query.answer("Você não possui a mutação Digestão de Minérios para fazer isso.", show_alert=True)
        return

    item = session.query(PlayerInventario).filter_by(id=inv_id, player_id=player.id, tipo_item="material").first()
    if not item or item.quantidade <= 0:
        session.close()
        await query.answer("Material não encontrado ou esgotado.", show_alert=True)
        return

    hp_max = player.hp_max or 24
    if (player.hp_atual or hp_max) >= hp_max:
        session.close()
        await query.answer("Seu HP já está no máximo!", show_alert=True)
        return

    CURA_VALOR = 10
    hp_antigo = player.hp_atual or hp_max
    player.hp_atual = min(hp_max, hp_antigo + CURA_VALOR)
    recuperado = player.hp_atual - hp_antigo

    nome_mat = item.nome_item
    if item.quantidade > 1:
        item.quantidade -= 1
    else:
        session.delete(item)

    session.commit()
    session.close()

    await query.answer(f"🩺 Você triturou e engoliu {nome_mat}! Recuperou +{recuperado} HP.", show_alert=True)
    await painel_materiais(update, context)


# ============================================================
# TELA 5: GRIMÓRIO (Magias e Artes Arcanas)
# ============================================================

async def painel_grimorio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    if not player:
        session.close()
        return

    mana_max = player.mana_max or 0
    mana_atual = player.mana_atual if player.mana_atual is not None else mana_max

    # Habilidade de classe (Ativa)
    hab_ativa = (
        session.query(HabilidadeAtiva)
        .filter_by(classe_id=player.classe_id)
        .first()
    )

    recurso_txt = f"🔷 Mana: *{mana_atual}/{mana_max}*" if mana_max > 0 else f"⚡ Vigor: *{player.vig_atual if player.vig_atual is not None else (player.vig_max or 60)}/{player.vig_max or 60}*"
    texto = (
        "📖 *Grimório & Artes Marciais*\n"
        f"{recurso_txt}\n\n"
    )

    if hab_ativa:
        rank = player.habilidade_ativa_nivel or 1
        dano_pct = getattr(hab_ativa, f"dano_pct_rank{rank}", hab_ativa.dano_pct_rank1)
        efeito_val = getattr(hab_ativa, f"efeito_secundario_rank{rank}", hab_ativa.efeito_secundario_rank1)
        icone_recurso = "⚡" if hab_ativa.recurso_tipo == "Vigor" else "🔷"
        val_str = f"+{int(efeito_val * 100)}%" if efeito_val < 5 else f"+{int(efeito_val)}"

        texto += (
            f"⚔️ *Técnica de Classe: {hab_ativa.habilidade_nome} (Rank {rank}/5)*\n"
            f"   🏷️ Tipo: {hab_ativa.tipo_acao}  |  {icone_recurso} Custo: {hab_ativa.custo_recurso} {hab_ativa.recurso_tipo}\n"
            f"   💥 Dano: *{int(dano_pct * 100)}%* do Ataque\n"
            f"   ✨ Efeito ({hab_ativa.efeito_secundario_tipo}): *{val_str}*\n"
        )
        if hab_ativa.descricao:
            texto += f"   📜 _{hab_ativa.descricao}_\n"
        texto += "\n"

    magias = (
        session.query(Magia)
        .filter(Magia.nivel_minimo <= (player.nivel or 1))
        .order_by(Magia.nivel_minimo)
        .all()
    )

    if magias:
        por_grau = {}
        for m in magias:
            por_grau.setdefault(m.grau or "Basico", []).append(m)

        for grau, lista in por_grau.items():
            texto += f"✨ *Grau {grau.capitalize()}:*\n"
            for m in lista:
                # Custo oficial da Roda de Magia (Básico 15%, Avançado 40%, Mestre 65% da Mana Máx; piso mínimo 1)
                custo = max(1, round(mana_max * CUSTO_POR_GRAU.get(m.grau, 0.15))) if mana_max else (m.custo_mana or 5)
                icone = ICONE_ELEMENTO.get(m.elemento, "✨")
                texto += (
                    f"• {icone} *{m.nome}* ({m.elemento})\n"
                    f"   🔷 Custo: {custo} Mana  |  💥 Dano Base: {m.dano or 15}\n"
                    f"   📜 Efeito: _{m.efeito or 'Dano Mágico'}_{f' — {m.lore}' if m.lore else ''}\n"
                )
            texto += "\n"
        texto += "💡 *Combate:* Magias são conjuradas durante confrontos através do botão ✨ *Magias*.\n"
    elif not hab_ativa:
        texto += (
            "📭 Seu grimório está em branco.\n"
            "Conforme você sobe de nível e aprofunda suas artes místicas, "
            "novos encantamentos serão inscritos nestas páginas."
        )
    else:
        texto += "💡 *Técnica Marcial:* Habilidades de combate são ativadas no confronto através do botão ⚡ *Habilidade*.\n"

    session.close()
    botoes = barra_navegacao_personagem("grimorio")
    botoes.append([InlineKeyboardButton("⬅️ Voltar ao Menu Principal", callback_data="menu_status")])
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


# ============================================================
# AÇÕES E CALLBACKS DO INVENTÁRIO
# ============================================================

def equipar_item_8slots(session, player, inv_item: PlayerInventario) -> tuple[bool, str]:
    """
    Equipa um item no slot corporal correto sem desequipar peças de outros slots:
    - Arma: desequipa apenas a arma anterior
    - Armadura (Elmo, Peitoral, Luvas, Calca, Bota, Escudo, Amuleto, Anel):
      desequipa apenas a peça que ocupa o MESMO slot.
    """
    if inv_item.tipo_item == "arma":
        outras_armas = (
            session.query(PlayerInventario)
            .filter_by(player_id=player.id, tipo_item="arma", equipado=True)
            .all()
        )
        for a in outras_armas:
            a.equipado = False
        inv_item.equipado = True
        return True, "Arma equipada com sucesso!"

    elif inv_item.tipo_item == "armadura":
        arm = session.query(Armadura).filter_by(id=inv_item.item_ref_id).first()
        slot_alvo = arm.slot if arm else "Peitoral"

        equipadas = (
            session.query(PlayerInventario)
            .filter_by(player_id=player.id, tipo_item="armadura", equipado=True)
            .all()
        )
        for eq in equipadas:
            eq_arm = session.query(Armadura).filter_by(id=eq.item_ref_id).first()
            if eq_arm and eq_arm.slot == slot_alvo:
                eq.equipado = False

        inv_item.equipado = True
        return True, f"{slot_alvo} equipado com sucesso!"

    elif inv_item.tipo_item == "acessorio":
        slot_alvo = "Anel" if "anel" in (inv_item.nome_item or "").lower() else "Amuleto"
        equipadas = (
            session.query(PlayerInventario)
            .filter(
                PlayerInventario.player_id == player.id,
                PlayerInventario.equipado == True,
                PlayerInventario.tipo_item.in_(["acessorio", "armadura"]),
            )
            .all()
        )
        for eq in equipadas:
            if eq.tipo_item == "acessorio":
                eq_slot = "Anel" if "anel" in (eq.nome_item or "").lower() else "Amuleto"
                if eq_slot == slot_alvo:
                    eq.equipado = False
            elif eq.tipo_item == "armadura":
                eq_arm = session.query(Armadura).filter_by(id=eq.item_ref_id).first()
                if eq_arm and eq_arm.slot == slot_alvo:
                    eq.equipado = False

        inv_item.equipado = True
        return True, f"Acessório ({slot_alvo}) equipado com sucesso!"

    return False, "Item não equipável."


async def alternar_equipar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    partes = query.data.split("_")
    acao = partes[1]
    inv_id = int(partes[2])

    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    item = session.query(PlayerInventario).filter_by(id=inv_id, player_id=player.id).first()
    if not item:
        await query.answer("Item não encontrado.", show_alert=True)
        session.close()
        return

    if acao == "equipar":
        ok, msg = equipar_item_8slots(session, player, item)
        await query.answer(msg, show_alert=True)
    else:
        item.equipado = False
        await query.answer(f"{item.nome_item} desequipado.", show_alert=True)

    session.commit()
    session.close()

    # Se veio da tela de equipamentos, volta pra equipamentos. Se veio da mochila, volta pra mochila.
    if acao == "desequipar":
        await painel_equipamentos(update, context)
    else:
        await painel_mochila(update, context)


async def usar_consumivel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    inv_id = int(query.data.split("_")[-1])

    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    item = session.query(PlayerInventario).filter_by(id=inv_id, player_id=player.id).first()
    if not item:
        await query.answer("Item não encontrado.", show_alert=True)
        session.close()
        return

    from db.models import Consumivel
    consumivel_ref = None
    if item.item_ref_id:
        consumivel_ref = session.query(Consumivel).filter_by(id=item.item_ref_id).first()
    from game.corrupcao import modificador_cura_corrupcao
    mod_cura = modificador_cura_corrupcao(player)

    if not consumivel_ref:
        # fallback pra itens legados sem item_ref_id
        nome = (item.nome_item or "").lower()
        if "cura" in nome or "vida" in nome or "hp" in nome:
            cura = max(1, int(round(25 * mod_cura)))
            hp_max = player.hp_max or 24
            hp_antigo = player.hp_atual or hp_max
            player.hp_atual = min(hp_max, hp_antigo + cura)
            rec = player.hp_atual - hp_antigo
            aviso_corr = f" (reduzido pela Corrupção)" if mod_cura < 1.0 else ""
            msg = f"🧪 Você bebeu {item.nome_item} e recuperou +{rec} HP!{aviso_corr}"
        elif "vigor" in nome or "energia" in nome:
            vig_max = player.vig_max or 60
            vig_antigo = player.vig_atual or vig_max
            player.vig_atual = min(vig_max, vig_antigo + 30)
            rec = player.vig_atual - vig_antigo
            msg = f"🧪 Você usou {item.nome_item} e recuperou +{rec} Vigor!"
        elif "mana" in nome and player.mana_max:
            mana_max = player.mana_max or 0
            mana_antigo = player.mana_atual or mana_max
            player.mana_atual = min(mana_max, mana_antigo + 20)
            rec = player.mana_atual - mana_antigo
            msg = f"🧪 Você bebeu {item.nome_item} e recuperou +{rec} Mana!"
        else:
            msg = f"🧪 Você consumiu {item.nome_item}."
    elif consumivel_ref.tipo == "cura":
        hp_max = player.hp_max or 24
        hp_antigo = player.hp_atual or hp_max
        qtd_base = consumivel_ref.quantidade_recuperada or 0
        cura = max(1, int(round(qtd_base * mod_cura)))
        player.hp_atual = min(hp_max, hp_antigo + cura)
        rec = player.hp_atual - hp_antigo
        aviso_corr = f" (reduzido pela Corrupção)" if mod_cura < 1.0 else ""
        msg = f"🧪 Você bebeu {item.nome_item} e recuperou +{rec} HP!{aviso_corr}"
    elif consumivel_ref.tipo == "mana" and player.mana_max:
        mana_max = player.mana_max or 0
        mana_antigo = player.mana_atual or mana_max
        player.mana_atual = min(mana_max, mana_antigo + (consumivel_ref.quantidade_recuperada or 0))
        rec = player.mana_atual - mana_antigo
        msg = f"🧪 Você bebeu {item.nome_item} e recuperou +{rec} Mana!"
    elif consumivel_ref.tipo == "antidoto":
        player.em_combate_efeito_jogador = None
        player.em_combate_efeito_jogador_turnos = None
        msg = f"🧪 Você usou {item.nome_item} e removeu os efeitos negativos leves!"
    else:
        msg = f"🧪 Você consumiu {item.nome_item}."

    if (item.quantidade or 1) > 1:
        item.quantidade -= 1
    else:
        session.delete(item)

    session.commit()
    session.close()
    await query.answer(msg, show_alert=True)
    await painel_mochila(update, context)


async def descartar_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    inv_id = int(query.data.split("_")[-1])

    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    item = session.query(PlayerInventario).filter_by(id=inv_id, player_id=player.id).first()
    if not item:
        await query.answer("Item não encontrado.", show_alert=True)
        session.close()
        return

    nome = item.nome_item
    session.delete(item)
    session.commit()
    session.close()
    await query.answer(f"🗑️ {nome} foi descartado da mochila.", show_alert=True)
    await painel_mochila(update, context)


# Alias de compatibilidade com menu_inventario antigo
menu_inventario = painel_perfil
