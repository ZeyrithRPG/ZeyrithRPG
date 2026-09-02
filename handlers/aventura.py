"""
Fase 2 — Aventura: explorar, encontrar monstro, combate.
"""
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.connection import get_session
from db.models import Player, Local, Tier, CurvaMestra, Monstro
from game.exploracao import custo_vig_exploracao, rolar_exploracao
from game.combat import resolver_ataque, chance_fuga


def _tier_numero(nome_tier: str, session) -> int:
    tiers = session.query(Tier).order_by(Tier.id).all()
    for i, t in enumerate(tiers, start=1):
        if t.nome == nome_tier:
            return i
    return 1


def _nome_do_tier(numero: int, session) -> str:
    tiers = session.query(Tier).order_by(Tier.id).all()
    if not tiers:
        return "Sucata Enferrujada"  # nunca deve acontecer, mas evita quebrar se acontecer
    idx = max(0, min(numero - 1, len(tiers) - 1))
    return tiers[idx].nome


def _curva(session, nivel: int) -> CurvaMestra:
    return session.query(CurvaMestra).filter_by(nivel=nivel).first()


def _local_do_player(session, player) -> Local:
    """
    Nunca devolve None: se o jogador estiver sem local (personagem antigo, dado
    faltando, local removido do jogo), ele volta pra Vila Inicial automaticamente.
    Isso evita que qualquer tela quebre por causa de dado ausente.
    """
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

    texto = (
        f"📍 *{local.nome}* ({local.tipo})\n"
        f"{local.descricao}\n\n"
        f"⚠️ Perigo: {local.perigo}/5\n"
        f"⚡ Vigor: {player.vig_atual}/{player.vig_max}\n\n"
        f"Custo pra explorar aqui: {custo_vig_exploracao(local.perigo)} VIG"
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
        session.close()
        await query.edit_message_text(
            "⚡ Vigor insuficiente pra explorar. Descanse antes de continuar.\n\n"
            "(Descanso ainda não foi implementado — chega numa fase futura.)"
        )
        return

    player.vig_atual -= custo
    resultado = rolar_exploracao(local.perigo)

    if resultado == "nada":
        session.commit()
        session.close()
        await query.edit_message_text(
            f"🌫️ Nada acontece dessa vez. (-{custo} VIG)\n\n"
            f"⚡ Vigor: {player.vig_atual}/{player.vig_max}",
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
        session.close()
        await query.edit_message_text(
            f"✨ Achado raro! Você encontra {achado_ouro} de Ouro no caminho.\n\n"
            f"💰 Ouro: {player.ouro}",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔍 Explorar de novo", callback_data="explorar")],
                 [InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return

    # Combate: comum / elite / ameaca_sup / boss
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
        session.close()
        await query.edit_message_text(
            "🌫️ Você ouve algo à distância, mas nada aparece.",
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

    texto = (
        f"⚔️ *{monstro.nome}* apareceu! ({monstro.papel}, {tier_nome})\n\n"
        f"❤️ HP do inimigo: {monstro.hp}/{monstro.hp}\n"
        f"🗡️ {monstro.golpe_especial}"
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

    linhas = []

    # jogador ataca
    res = resolver_ataque(atq_bonus_jogador, monstro.defesa, dano_jogador_base)
    if res.acertou:
        player.em_combate_hp_monstro -= res.dano
        linhas.append(f"⚔️ Você acerta{' (CRÍTICO!)' if res.critico else ''}: {res.dano} de dano.")
    else:
        linhas.append("⚔️ Você errou o golpe.")

    if player.em_combate_hp_monstro <= 0:
        xp_ganho = 10 * player.tier_mais_alto_alcancado
        ouro_ganho = random.randint(5, 15) * player.tier_mais_alto_alcancado
        player.xp_atual += xp_ganho
        player.ouro += ouro_ganho
        player.em_combate_monstro_id = None
        player.em_combate_hp_monstro = None
        session.commit()
        nome_derrotado = monstro.nome
        session.close()
        await query.edit_message_text(
            "\n".join(linhas) + f"\n\n🏆 Você derrotou {nome_derrotado}!\n"
            f"✨ +{xp_ganho} XP | 💰 +{ouro_ganho} Ouro",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return

    # monstro contra-ataca
    res_m = resolver_ataque(monstro.atq_bonus, defesa_jogador, monstro.dano)
    if res_m.acertou:
        player.hp_atual -= res_m.dano
        linhas.append(f"💥 {monstro.nome} acerta{' (CRÍTICO!)' if res_m.critico else ''}: {res_m.dano} de dano em você.")
    else:
        linhas.append(f"💨 {monstro.nome} errou o ataque.")

    if player.hp_atual <= 0:
        player.hp_atual = 1  # sem risco de morte permanente ainda (Fase 2)
        player.em_combate_monstro_id = None
        player.em_combate_hp_monstro = None
        session.commit()
        session.close()
        await query.edit_message_text(
            "\n".join(linhas) + "\n\n☠️ Você quase morreu e recua do combate, ferido.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")]]
            ),
        )
        return

    session.commit()
    hp_monstro = player.em_combate_hp_monstro
    hp_jogador = player.hp_atual
    session.close()
    await query.edit_message_text(
        "\n".join(linhas) +
        f"\n\n❤️ Você: {hp_jogador} | ❤️ {monstro.nome}: {hp_monstro}",
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
            "🏃 Você fugiu com sucesso.",
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
    texto = "🏃 Fuga falhou!"
    if res_m.acertou:
        player.hp_atual -= res_m.dano
        texto += f" {monstro.nome} acerta um golpe livre: {res_m.dano} de dano."
    session.commit()
    hp_jogador = player.hp_atual
    session.close()
    await query.edit_message_text(
        texto + f"\n\n❤️ Você: {hp_jogador}",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⚔️ Atacar", callback_data="atacar"),
              InlineKeyboardButton("🏃 Fugir", callback_data="fugir")]]
        ),
    )
