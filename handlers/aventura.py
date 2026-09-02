"""
Fase 2 — Aventura: explorar, encontrar monstro, combate.
Visual denso, com ícone em cada linha de informação (padrão Pixel Realm).
"""
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.connection import get_session
from db.models import Player, Local, Tier, CurvaMestra, Monstro
from game.exploracao import custo_vig_exploracao, rolar_exploracao
from game.combat import resolver_ataque, chance_fuga

ICONE_TIPO_LOCAL = {
    "Cidade": "🏰", "Estrada Perigosa": "🛤️", "Mina": "⛏️", "Dungeon": "🕸️",
    "Ruina": "🏛️", "Floresta Perigosa": "🌲", "Caverna": "🕳️",
    "Planicie Selvagem": "🌾", "Fenda": "🌋", "Campo de Batalha": "⚔️",
    "Pantano": "🐊", "Covil de Boss": "💀", "Ritual": "🔮", "Portal": "🌀",
}
ICONE_PAPEL = {"Comum": "⚪", "Elite": "🟣", "Boss": "🔴", "Cosmico": "⚫"}
BARRA_PERIGO = {1: "🟢", 2: "🟢", 3: "🟡", 4: "🟠", 5: "🔴"}


def _barra(atual, maximo, tamanho=10, cheio="🟩", vazio="⬛"):
    if not maximo:
        return vazio * tamanho
    n = round(tamanho * max(0, min(atual, maximo)) / maximo)
    return cheio * n + vazio * (tamanho - n)


def _tier_numero(nome_tier, session):
    tiers = session.query(Tier).order_by(Tier.id).all()
    for i, t in enumerate(tiers, start=1):
        if t.nome == nome_tier:
            return i
    return 1


def _nome_do_tier(numero, session):
    tiers = session.query(Tier).order_by(Tier.id).all()
    if not tiers:
        return "Sucata Enferrujada"
    idx = max(0, min(numero - 1, len(tiers) - 1))
    return tiers[idx].nome


def _curva(session, nivel):
    return session.query(CurvaMestra).filter_by(nivel=nivel).first()


def _local_do_player(session, player):
    local = None
    if player.local_atual:
        local = session.query(Local).filter_by(nome=player.local_atual).first()
    if local is None:
        local = session.query(Local).filter_by(nome="Vila Inicial").first()
        if local is None:
            local = session.query(Local).order_by(Local.id).first()
        if local is not None:
            player.local_atual = local.nome
            session.commit()
    return local


# ---------- Menu Aventura ----------

async def menu_aventura(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    local = _local_do_player(session, player)
    icone_local = ICONE_TIPO_LOCAL.get(local.tipo, "📍")
    barra_perigo = BARRA_PERIGO.get(local.perigo, "🟡") * local.perigo + "⬛" * (5 - local.perigo)
    custo = custo_vig_exploracao(local.perigo)

    vig_atual, vig_max = player.vig_atual, player.vig_max

    texto = (
        f"{icone_local} *{local.nome}*\n"
        f"_{local.tipo} · perto de {local.cidade_proxima}_\n\n"
        f"{local.descricao}\n\n"
        f"⚠️ Perigo: {barra_perigo} ({local.perigo}/5)\n"
        f"⚡ Vigor: {vig_atual}/{vig_max}\n"
        f"{_barra(vig_atual, vig_max)}\n\n"
        f"🔍 Custo pra explorar aqui: *{custo} VIG*"
    )
    botoes = [[InlineKeyboardButton("🔍 Explorar", callback_data="explorar")],
              [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


# ---------- Explorar ----------

async def explorar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    local = _local_do_player(session, player)

    custo = custo_vig_exploracao(local.perigo)
    if player.vig_atual < custo:
        vig_atual, vig_max = player.vig_atual, player.vig_max
        session.close()
        await query.edit_message_text(
            f"⚡ *Vigor insuficiente* pra explorar aqui.\n\n"
            f"⚡ Vigor: {vig_atual}/{vig_max}\n"
            f"🔍 Precisa de: {custo} VIG\n\n"
            "_(Descanso ainda não foi implementado — chega numa fase futura.)_",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return

    player.vig_atual -= custo
    resultado = rolar_exploracao(local.perigo)
    icone_local = ICONE_TIPO_LOCAL.get(local.tipo, "📍")

    if resultado == "nada":
        session.commit()
        nome_local, vig_atual, vig_max = local.nome, player.vig_atual, player.vig_max
        session.close()
        await query.edit_message_text(
            f"{icone_local} *{nome_local}*\n\n"
            f"🌫️ Nada de interessante dessa vez. (-{custo} VIG)\n\n"
            f"⚡ Vigor: {vig_atual}/{vig_max}\n{_barra(vig_atual, vig_max)}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔍 Explorar de novo", callback_data="explorar")],
                 [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return

    if resultado == "achado":
        achado_ouro = random.randint(5, 20) * player.tier_mais_alto_alcancado
        player.ouro += achado_ouro
        session.commit()
        ouro_total, vig_atual, vig_max = player.ouro, player.vig_atual, player.vig_max
        session.close()
        await query.edit_message_text(
            f"✨ *Achado raro!*\n\n"
            f"Você encontra {achado_ouro} de Ouro escondido no caminho.\n\n"
            f"💰 Ouro total: {ouro_total}\n"
            f"⚡ Vigor: {vig_atual}/{vig_max}\n{_barra(vig_atual, vig_max)}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔍 Explorar de novo", callback_data="explorar")],
                 [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return

    tier_num = player.tier_mais_alto_alcancado
    papel = {"comum": "Comum", "elite": "Elite", "boss": "Boss", "ameaca_sup": "Elite"}[resultado]
    if resultado == "ameaca_sup":
        tier_num = min(tier_num + 1, 14)

    tier_nome = _nome_do_tier(tier_num, session)
    candidatos = session.query(Monstro).filter_by(tier=tier_nome, papel=papel).all()
    if not candidatos:
        candidatos = session.query(Monstro).filter_by(tier=tier_nome, papel="Comum").all()
    if not candidatos:
        candidatos = session.query(Monstro).filter_by(tier=tier_nome).all()
    if not candidatos:
        session.commit()
        nome_local, vig_atual, vig_max = local.nome, player.vig_atual, player.vig_max
        session.close()
        await query.edit_message_text(
            f"{icone_local} *{nome_local}*\n\n🌫️ Você ouve algo à distância, mas nada aparece.\n\n"
            f"⚡ Vigor: {vig_atual}/{vig_max}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔍 Explorar de novo", callback_data="explorar")],
                 [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return
    monstro = random.choice(candidatos)

    player.em_combate_monstro_id = monstro.id
    player.em_combate_hp_monstro = monstro.hp
    session.commit()

    icone_papel = ICONE_PAPEL.get(monstro.papel, "⚪")
    vig_atual, vig_max = player.vig_atual, player.vig_max
    texto = (
        f"⚔️ *COMBATE INICIADO*\n"
        f"{icone_local} {local.nome}\n\n"
        f"{icone_papel} *{monstro.nome}* — Nv.{monstro.nivel} ({monstro.papel})\n"
        f"❤️ {monstro.hp}/{monstro.hp}\n{_barra(monstro.hp, monstro.hp, cheio='🟥')}\n\n"
        f"🗡️ Golpe: {monstro.golpe_especial}\n\n"
        f"⚡ Seu Vigor: {vig_atual}/{vig_max}"
    )
    session.close()
    await query.edit_message_text(
        texto, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⚔️ Atacar", callback_data="atacar"),
              InlineKeyboardButton("🏃 Fugir", callback_data="fugir")]]
        ),
    )


# ---------- Combate ----------

async def atacar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    monstro = session.get(Monstro, player.em_combate_monstro_id) if player.em_combate_monstro_id else None
    if monstro is None or player.em_combate_hp_monstro is None:
        session.close()
        await query.edit_message_text(
            "Esse combate não está mais ativo.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return
    tier_jogador = session.query(Tier).filter(
        Tier.id == player.tier_mais_alto_alcancado
    ).first()
    curva = _curva(session, player.nivel)

    dano_jogador_base = tier_jogador.dano_comum if tier_jogador else 4
    atq_bonus_jogador = curva.atq_bonus if curva else 2
    defesa_jogador = curva.defesa_esperada if curva else 6
    icone_papel = ICONE_PAPEL.get(monstro.papel, "⚪")

    linhas = []

    res = resolver_ataque(atq_bonus_jogador, monstro.defesa, dano_jogador_base)
    if res.acertou:
        player.em_combate_hp_monstro -= res.dano
        linhas.append(f"⚔️ Você acerta{' 💥 CRÍTICO!' if res.critico else ''}: *{res.dano}* de dano.")
    else:
        linhas.append("💨 Você errou o golpe.")

    if player.em_combate_hp_monstro <= 0:
        xp_ganho = 10 * player.tier_mais_alto_alcancado
        ouro_ganho = random.randint(5, 15) * player.tier_mais_alto_alcancado
        player.xp_atual += xp_ganho
        player.ouro += ouro_ganho
        player.em_combate_monstro_id = None
        player.em_combate_hp_monstro = None
        session.commit()
        nome_derrotado, ouro_total, xp_total = monstro.nome, player.ouro, player.xp_atual
        session.close()
        await query.edit_message_text(
            "\n".join(linhas) +
            f"\n\n🏆 *Você derrotou {nome_derrotado}!*\n\n"
            f"✨ +{xp_ganho} XP (total: {xp_total})\n"
            f"💰 +{ouro_ganho} Ouro (total: {ouro_total})",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return

    res_m = resolver_ataque(monstro.atq_bonus, defesa_jogador, monstro.dano)
    if res_m.acertou:
        player.hp_atual -= res_m.dano
        linhas.append(f"💥 {monstro.nome} acerta{' (CRÍTICO!)' if res_m.critico else ''}: *{res_m.dano}* de dano em você.")
    else:
        linhas.append(f"💨 {monstro.nome} errou o ataque.")

    if player.hp_atual <= 0:
        player.hp_atual = 1
        player.em_combate_monstro_id = None
        player.em_combate_hp_monstro = None
        session.commit()
        session.close()
        await query.edit_message_text(
            "\n".join(linhas) + "\n\n☠️ *Você quase morreu* e recua do combate, ferido.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return

    session.commit()
    hp_monstro, hp_monstro_max = player.em_combate_hp_monstro, monstro.hp
    hp_jogador, hp_jogador_max = player.hp_atual, player.hp_max
    nome_monstro, papel_monstro, nivel_monstro = monstro.nome, monstro.papel, monstro.nivel
    session.close()
    await query.edit_message_text(
        f"{icone_papel} *{nome_monstro}* Nv.{nivel_monstro} ({papel_monstro})\n"
        f"❤️ {hp_monstro}/{hp_monstro_max}\n{_barra(hp_monstro, hp_monstro_max, cheio='🟥')}\n\n"
        + "\n".join(linhas) +
        f"\n\n🧍 Você\n❤️ {hp_jogador}/{hp_jogador_max}\n{_barra(hp_jogador, hp_jogador_max)}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⚔️ Atacar", callback_data="atacar"),
              InlineKeyboardButton("🏃 Fugir", callback_data="fugir")]]
        ),
    )


async def fugir(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    if chance_fuga():
        player.em_combate_monstro_id = None
        player.em_combate_hp_monstro = None
        session.commit()
        session.close()
        await query.edit_message_text(
            "🏃 *Você fugiu com sucesso.*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return

    monstro = session.get(Monstro, player.em_combate_monstro_id) if player.em_combate_monstro_id else None
    if monstro is None:
        session.close()
        await query.edit_message_text(
            "Esse combate não está mais ativo.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return

    curva = _curva(session, player.nivel)
    defesa_jogador = curva.defesa_esperada if curva else 6
    res_m = resolver_ataque(monstro.atq_bonus, defesa_jogador, monstro.dano)
    texto = "🏃 *Fuga falhou!*"
    if res_m.acertou:
        player.hp_atual -= res_m.dano
        texto += f"\n{monstro.nome} acerta um golpe livre: *{res_m.dano}* de dano."
    session.commit()
    hp_jogador, hp_jogador_max = player.hp_atual, player.hp_max
    session.close()
    await query.edit_message_text(
        texto + f"\n\n❤️ Você: {hp_jogador}/{hp_jogador_max}\n{_barra(hp_jogador, hp_jogador_max)}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⚔️ Atacar", callback_data="atacar"),
              InlineKeyboardButton("🏃 Fugir", callback_data="fugir")]]
        ),
    )
