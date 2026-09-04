"""
Fase 2.5 — Magias no combate. Usa os dados reais da aba Magia e Habilidades,
dano derivado da Curva Mestra (mesma fórmula do dano de arma, só multiplicador
diferente) — sem matemática paralela, como já fechamos.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.connection import get_session
from db.models import Player, Magia, Monstro, CurvaMestra
from game.combat import resolver_ataque

ICONE_ELEMENTO = {
    "Fogo": "🔥", "Gelo": "❄️", "Raio": "⚡", "Sombra": "🌑", "Luz": "✨", "Arcano": "🔮",
}
CUSTO_POR_GRAU = {"Basico": 0.15, "Avancado": 0.4, "Mestre": 0.65}


async def menu_magias(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    if not player.em_combate_monstro_id:
        session.close()
        await query.answer("Só dá pra conjurar durante um combate.", show_alert=True)
        return

    mana_max = player.mana_max or 0
    magias_disponiveis = session.query(Magia).filter(
        Magia.nivel_minimo <= (player.nivel or 1)
    ).order_by(Magia.nivel_minimo).all()

    if not magias_disponiveis or mana_max == 0:
        session.close()
        await query.answer("Você não conhece nenhuma magia ainda.", show_alert=True)
        return

    linhas = [f"🔷 Mana: {player.mana_atual}/{mana_max}\n"]
    botoes = []
    for m in magias_disponiveis:
        custo_real = round(mana_max * CUSTO_POR_GRAU.get(m.grau, 0.15))
        icone = ICONE_ELEMENTO.get(m.elemento, "✨")
        pode_pagar = player.mana_atual >= custo_real
        linhas.append(f"{icone} *{m.nome}* ({m.grau}) — custo {custo_real} mana{'  ❌' if not pode_pagar else ''}")
        if pode_pagar:
            botoes.append([InlineKeyboardButton(f"{icone} {m.nome}", callback_data=f"magia_{m.id}")])
    botoes.append([InlineKeyboardButton("⬅️ Voltar ao combate", callback_data="voltar_combate")])

    session.close()
    await query.edit_message_text(
        "✨ *Suas Magias*\n\n" + "\n".join(linhas),
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(botoes),
    )


async def conjurar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    magia_id = int(query.data.split("_")[1])

    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    magia = session.get(Magia, magia_id)
    monstro = session.get(Monstro, player.em_combate_monstro_id) if player.em_combate_monstro_id else None

    if magia is None or monstro is None or player.em_combate_hp_monstro is None:
        session.close()
        await query.edit_message_text(
            "Esse combate não está mais ativo.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]),
        )
        return

    curva = session.query(CurvaMestra).filter_by(nivel=player.nivel or 1).first()
    mana_max = player.mana_max or 0
    custo_real = round(mana_max * CUSTO_POR_GRAU.get(magia.grau, 0.15))

    if player.mana_atual < custo_real:
        session.close()
        await query.answer("Mana insuficiente.", show_alert=True)
        return

    player.mana_atual -= custo_real
    atq_bonus_jogador = curva.atq_bonus if curva else 2

    res = resolver_ataque(atq_bonus_jogador, monstro.defesa, magia.dano)
    linhas = [f"{ICONE_ELEMENTO.get(magia.elemento,'✨')} Você conjura *{magia.nome}*!"]
    if res.acertou:
        player.em_combate_hp_monstro -= res.dano
        linhas.append(f"💥 Acerto{' CRÍTICO' if res.critico else ''}: *{res.dano}* de dano mágico.")
    else:
        linhas.append("💨 A magia erra o alvo.")

    if player.em_combate_hp_monstro <= 0:
        xp_ganho = 10 * player.tier_mais_alto_alcancado
        ouro_ganho = 10 * player.tier_mais_alto_alcancado
        player.xp_atual += xp_ganho
        player.ouro += ouro_ganho
        nome_derrotado = monstro.nome
        player.em_combate_monstro_id = None
        player.em_combate_hp_monstro = None
        session.commit()
        session.close()
        await query.edit_message_text(
            "\n".join(linhas) + f"\n\n🏆 *Você derrotou {nome_derrotado}!*\n✨ +{xp_ganho} XP  💰 +{ouro_ganho} Ouro",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]),
        )
        return

    defesa_jogador = curva.defesa_esperada if curva else 6
    res_m = resolver_ataque(monstro.atq_bonus, defesa_jogador, monstro.dano)
    if res_m.acertou:
        player.hp_atual -= res_m.dano
        linhas.append(f"💥 {monstro.nome} contra-ataca: *{res_m.dano}* de dano.")
    else:
        linhas.append(f"💨 {monstro.nome} errou.")

    session.commit()
    hp_m, hp_m_max = player.em_combate_hp_monstro, monstro.hp
    hp_j, hp_j_max = player.hp_atual, player.hp_max
    mana_atual = player.mana_atual
    session.close()
    await query.edit_message_text(
        "\n".join(linhas) + f"\n\n❤️ {monstro.nome}: {hp_m}/{hp_m_max}\n"
        f"🧍 Você: {hp_j}/{hp_j_max}  ·  🔷 Mana: {mana_atual}/{mana_max}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⚔️ Atacar", callback_data="atacar"),
              InlineKeyboardButton("✨ Magias", callback_data="menu_magias")],
             [InlineKeyboardButton("🏃 Fugir", callback_data="fugir")]]
        ),
    )
