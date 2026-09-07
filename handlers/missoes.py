"""
Fase 5 — Missões e Facções/Títulos.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.connection import get_session
from db.models import Player, Tier, PlayerQuest, Missao
from game.missoes import (
    listar_missoes_disponiveis, aceitar_missao, completar_missao,
    honra_do_player, TIER_PARA_FACCAO, ErroMissao, barra_compacta,
    checar_e_executar_reset_diario, reroll_missao, tiers_do_polo_atual,
)
from game.titulos import listar_titulos_do_player, listar_todos_titulos, equipar_titulo


def _tier_do_player(session, player):
    tiers = session.query(Tier).order_by(Tier.id).all()
    idx = max(0, min((player.tier_mais_alto_alcancado or 1) - 1, len(tiers) - 1))
    return tiers[idx].nome if tiers else "Sucata Enferrujada"


# ---------- Menu de Missões / Mural da Milícia ----------

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

    # Dispara o reset diário se for novo dia
    checar_e_executar_reset_diario(session, player)

    tier_nome = _tier_do_player(session, player)
    faccao = TIER_PARA_FACCAO.get(tier_nome)
    honra = honra_do_player(session, player, faccao) if faccao else 0

    from game.mapa import cidade_polo_do_local
    cidade_polo = cidade_polo_do_local(session, player.local_atual or "Vila Inicial")
    nome_polo = cidade_polo.nome if cidade_polo else "Polo Inicial"

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
        texto = (
            f"📜 *Mural da Milícia — Contratos Diários*\n"
            f"📍 Polo: {nome_polo} ({tier_nome})\n"
            f"🏛️ Honra com {faccao}: *{honra}*\n"
            f"🎲 Rerolls disponíveis hoje: *{player.rerolls_restantes or 0}/2*\n"
            f"══════════════════════════\n\n"
        )
        botoes = []

        if em_andamento:
            texto += "*📋 Contratos em Andamento:*\n"
            for pq in em_andamento:
                m = session.query(Missao).filter_by(id=pq.quest_id).first()
                if not m:
                    continue
                tipo_icone = "⚔️" if pq.tipo_objetivo == "abate" else ("🧺" if pq.tipo_objetivo == "coleta" else "🔸")
                prog = pq.progresso_atual or 0
                meta = pq.progresso_meta or 1
                barra = barra_compacta(prog, meta, blocos=3)
                completo = prog >= meta

                texto += (
                    f"{tipo_icone} *{m.nome}*\n"
                    f"   ↳ Alvo: _{pq.alvo_id_ou_nome or m.nome}_\n"
                    f"   ↳ Progresso: {barra} `{prog}/{meta}`"
                    f"{'  (Pronto! ✅)' if completo else ''}\n"
                )
                if m.recompensa and str(m.recompensa).strip() not in ("0", "None", ""):
                    r_str = str(m.recompensa).strip()
                    rec_label = f"{r_str} Ouro" if r_str.isdigit() else r_str
                    texto += f"   ↳ Recompensa: 💰 {rec_label}\n\n"
                else:
                    texto += "\n"

                # Trava contra entrega cega
                if completo:
                    botoes.append([InlineKeyboardButton(
                        f"🎁 Entregar: {m.nome} ({prog}/{meta})",
                        callback_data=f"miss_entregar_{m.id}",
                    )])
                else:
                    botoes.append([InlineKeyboardButton(
                        f"🔒 Incompleto: {m.nome} ({prog}/{meta})",
                        callback_data=f"miss_bloqueada_{m.id}",
                    )])

                # Botão de reroll se ainda tiver rerolls diários
                if (player.rerolls_restantes or 0) > 0 and not completo:
                    botoes.append([InlineKeyboardButton(
                        f"🎲 Reroll neste contrato ({player.rerolls_restantes} restantes)",
                        callback_data=f"miss_reroll_{m.id}",
                    )])

        if principais:
            texto += "⭐ *Missão Principal do Tier:*\n"
            for m in principais:
                rec_txt = ""
                if m.recompensa and str(m.recompensa).strip() not in ("0", "None", ""):
                    r_str = str(m.recompensa).strip()
                    if r_str.isdigit() and int(r_str) > 0:
                        rec_txt = f"💰 {r_str} Ouro  ·  "
                    elif "ouro" in r_str.lower():
                        rec_txt = f"💰 {r_str}  ·  "
                    else:
                        rec_txt = f"🎁 {r_str}  ·  "
                texto += f"👑 *{m.nome}*\n_{m.objetivo}_\n{rec_txt}✨ +{m.recompensa_xp or 0} XP\n\n"
                botoes.append([InlineKeyboardButton(f"⭐ Aceitar Principal: {m.nome}", callback_data=f"miss_aceitar_{m.id}")])

        if por_categoria:
            texto += "📂 *Outras Missões por Categoria:*"
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
        recompensa_txt = str(m.recompensa).strip() if m.recompensa else ""
        if recompensa_txt and recompensa_txt not in ("0", "None"):
            if recompensa_txt.isdigit():
                if int(recompensa_txt) > 0:
                    texto += f"💰 {recompensa_txt} Ouro\n"
            elif "ouro" in recompensa_txt.lower():
                texto += f"💰 {recompensa_txt}\n"
            else:
                texto += f"🎁 Recompensa: {recompensa_txt}\n"
        if m.recompensa_extra:
            texto += f"🎁 {m.recompensa_extra}\n"
        botoes.append([InlineKeyboardButton(f"Aceitar: {m.nome}", callback_data=f"miss_aceitar_{m.id}")])
    botoes.append([InlineKeyboardButton("⬅️ Voltar ao Mural", callback_data="menu_missoes")])
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
        await query.answer("✅ Missão aceita com sucesso!", show_alert=True)
    except ErroMissao as e:
        await query.answer(f"❌ {e}", show_alert=True)
    session.close()
    query.data = "menu_missoes"
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
        texto = f"✅ *Contrato cumprido e recompensado!*\n\n💰 +{ouro} Ouro"
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
                [[InlineKeyboardButton("⬅️ Voltar ao Mural", callback_data="menu_missoes")]]
            ),
        )
    except ErroMissao as e:
        await query.answer(f"❌ {e}", show_alert=True)
        session.close()


async def cb_reroll_missao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    missao_id = int(query.data.split("_")[-1])
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    try:
        nova = reroll_missao(session, player, missao_id)
        await query.answer(f"🎲 Contrato trocado por: {nova.nome}!", show_alert=True)
    except ErroMissao as e:
        await query.answer(f"❌ {e}", show_alert=True)
    session.close()
    query.data = "menu_missoes"
    await menu_missoes(update, context)


async def cb_missao_bloqueada(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔒 Esse contrato ainda não foi concluído! Complete o objetivo antes de entregar.", show_alert=True)


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

    desbloqueados = listar_titulos_do_player(session, player)
    ids_desbloqueados = {t.id for t in desbloqueados}
    todos = listar_todos_titulos(session)

    titulo_atual = player.titulo_ativo or "Nenhum"

    texto = (
        "🏆 *Títulos & Honrarias*\n\n"
        f"🎖️ Título Ativo: *{titulo_atual}*\n"
        "_O título equipado é exibido na sua ficha e comunica seus feitos aos NPCs._\n\n"
    )

    botoes = []

    if desbloqueados:
        texto += "*✨ Títulos Desbloqueados:*\n"
        for t in desbloqueados:
            ativo = (player.titulo_ativo == t.nome)
            status_icone = "🟢 [Equipado]" if ativo else "⚪"
            texto += f"{status_icone} *{t.nome}*\n   ↳ 🎁 {t.bonus}\n"
            if ativo:
                botoes.append([InlineKeyboardButton(f"❌ Desequipar: {t.nome}", callback_data="titulo_equipar_0")])
            else:
                botoes.append([InlineKeyboardButton(f"🎖️ Equipar: {t.nome}", callback_data=f"titulo_equipar_{t.id}")])
        texto += "\n"
    else:
        texto += "*✨ Títulos Desbloqueados:* Nenhum ainda.\n\n"

    bloqueados = [t for t in todos if t.id not in ids_desbloqueados]
    if bloqueados:
        texto += "*🔒 Títulos a Conquistar:*\n"
        for t in bloqueados[:8]:
            texto += f"🔒 *{t.nome}*\n   ↳ Requisito: _{t.condicao}_\n"

    botoes.append([InlineKeyboardButton("⬅️ Voltar às Facções", callback_data="menu_faccoes")])
    botoes.append([InlineKeyboardButton("⬅️ Voltar ao Status", callback_data="menu_status")])
    session.close()

    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def cb_equipar_titulo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    tid = int(query.data.split("_")[-1])
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    try:
        t = equipar_titulo(session, player, None if tid == 0 else tid)
        msg = f"✅ Título '{t.nome}' equipado!" if t else "✅ Título desequipado."
        await query.answer(msg, show_alert=True)
    except Exception as e:
        await query.answer(f"❌ {e}", show_alert=True)

    session.close()
    await menu_titulos(update, context)
