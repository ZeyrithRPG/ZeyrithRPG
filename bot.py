"""
A Infecção que Segura o Mundo — bot de Telegram
Fase 1: criação de personagem + HUD de status.
"""
import os
import logging
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters, PicklePersistence,
)
from telegram.helpers import escape_markdown
from dotenv import load_dotenv

from db.connection import get_session
from db.models import Player, Classe, CurvaMestra, Narrativa
from db.import_data import importar as importar_dados_do_jogo
from game.ui_utils import barra
from handlers.aventura import menu_aventura, explorar, atacar, fugir, voltar_combate, lootear, poupar, descansar_handler, habilidade_ativa_fisica_handler
from handlers.magias import menu_magias, conjurar, habilidade_ativa_magica_handler
from handlers.comercio import (
    menu_comercio, listar_compra, confirmar_compra, listar_venda, confirmar_venda,
    vender_tudo_callback, menu_crafting, confirmar_forja, confirmar_comprar_diagrama,
    menu_treinador, confirmar_upgrade_rank, listar_pocoes, confirmar_compra_pocao,
    menu_curandeiro, curar_hp_curandeiro, tratar_ferimento_curandeiro, purificar_curandeiro,
)
from handlers.inventario import (
    menu_inventario, painel_perfil, painel_equipamentos, painel_mochila,
    painel_materiais, painel_grimorio, alternar_equipar, usar_consumivel,
    descartar_item, purificar_ficha_handler, consumir_material_mutacao,
)
from handlers.missoes import (
    menu_missoes, cb_aceitar_missao, cb_entregar_missao, cb_reroll_missao,
    cb_missao_bloqueada, menu_faccoes, menu_titulos, cb_equipar_titulo,
)
from handlers.mapa import menu_mapa, viajar_local, mapa_regional, mapa_global, mapa_ir_cidade, mapa_atravessar_portao
from handlers.codex import (
    menu_codex, codex_bestiario_tiers, codex_bestiario_lista, codex_monstro_detalhe,
    codex_locais, codex_materiais,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

NOME, CLASSE = range(2)

ICONE_CLASSE = {
    "Guerreiro da Forja": "🛡️", "Inquisidor de Prata": "✝️", "Conjurador de Sangue (Hemomante)": "🩸",
    "Batedor dos Ecos": "🏹", "Ladino das Sombras": "🗡️", "Mago Elemental": "🔥",
    "Bárbaro da Fenda": "🪓", "Artífice Mecânico": "⚙️",
}


# ---------- /start ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    session.close()

    if player:
        await mostrar_hud(update, context)
        return ConversationHandler.END

    session2 = get_session()
    abertura = session2.query(Narrativa).filter_by(tipo="Abertura").first()
    session2.close()
    if abertura:
        await update.message.reply_text(f"🌍 *{abertura.titulo}*\n\n{abertura.texto}", parse_mode="Markdown")

    await update.message.reply_text(
        "Antes de começar, como se chama seu personagem?",
        parse_mode="Markdown",
    )
    return NOME


# ---------- /reset (Comando de Desenvolvedor) ----------

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    tg_id = str(update.effective_user.id)
    from game.atributos import deletar_player_cascata
    session = get_session()
    deletado = deletar_player_cascata(session, tg_id)
    session.close()

    context.user_data.clear()

    texto_reset = "🔄 *Personagem e progresso resetados com sucesso!*\n\n" if deletado else "ℹ️ Você não possuía nenhum personagem ativo.\n\n"

    session2 = get_session()
    abertura = session2.query(Narrativa).filter_by(tipo="Abertura").first()
    session2.close()
    if abertura:
        texto_reset += f"🌍 *{abertura.titulo}*\n\n{abertura.texto}\n\n"

    texto_reset += "Antes de começar sua nova jornada, como se chama seu personagem?"

    if query and query.message:
        await query.message.reply_text(texto_reset, parse_mode="Markdown")
    elif update.message:
        await update.message.reply_text(texto_reset, parse_mode="Markdown")
    return NOME


def calcular_faixa_progressao(classe):
    """Calcula a faixa aproximada de ganho de HP e Mana por nível coerente com hp_mult e mana_mult."""
    hp_mult = classe.hp_mult if classe.hp_mult is not None else 1.0
    mana_mult = classe.mana_mult if classe.mana_mult is not None else 1.0

    ganho_hp = 2.6 * hp_mult
    ganho_mana = 1.5 * mana_mult

    if ganho_hp >= 3.0:
        hp_faixa = "~3 a 4"
    elif ganho_hp >= 2.5:
        hp_faixa = "~2 a 3"
    else:
        hp_faixa = "~2"

    if ganho_mana >= 2.3:
        mana_faixa = "~2 a 3"
    elif ganho_mana >= 1.8:
        mana_faixa = "~2"
    elif ganho_mana >= 1.3:
        mana_faixa = "~1 a 2"
    else:
        mana_faixa = "~1"

    return hp_faixa, mana_faixa


def formatar_efeito_rank1(hab):
    """Retorna a descrição curta e objetiva do efeito de Rank 1 da habilidade ativa."""
    if not hab:
        return ""
    tipo = hab.efeito_secundario_tipo
    val = hab.efeito_secundario_rank1
    v_int = int(val) if val == int(val) else val
    custo = f"Custo: {hab.custo_recurso} {hab.recurso_tipo} · Dano {hab.dano_pct_rank1}x"

    if tipo == "atordoamento_chance_pct":
        efeito = f"{v_int}% de chance de atordoar por 1 turno"
    elif tipo == "reducao_dano_recebido_pct":
        efeito = f"Mitiga {v_int}% do dano recebido por 2 turnos"
    elif tipo == "cura_pct_dano":
        efeito = f"Cura {v_int}% do dano causado"
    elif tipo == "perfuracao_defesa_pts":
        efeito = f"Perfura {v_int} ponto{'s' if v_int > 1 else ''} de Defesa do alvo"
    elif tipo == "execucao_hp_baixo_pct":
        efeito = f"+{v_int}% de dano se alvo com HP ≤ 30%"
    elif tipo == "queimadura_dot_pct":
        efeito = f"Queimadura contínua ({v_int}% do dano) por 2 turnos"
    elif tipo == "furia_dano_causado_pct":
        efeito = f"Fúria (+{v_int}% de dano causado por 2 turnos)"
    elif tipo == "sangramento_dot_pct":
        efeito = f"Sangramento contínuo ({v_int}% do dano) por 2 turnos"
    else:
        efeito = hab.descricao or ""

    return f"{custo} — {efeito}"


async def receber_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nome_personagem"] = update.message.text.strip()

    session = get_session()
    classes = session.query(Classe).all()
    botoes = [
        [InlineKeyboardButton(f"{c.emoji or ICONE_CLASSE.get(c.nome, '⚔️')} {c.nome}", callback_data=f"classe_{c.id}")]
        for c in classes
    ]
    session.close()

    await update.message.reply_text(
        f"Bem-vindo, {context.user_data['nome_personagem']}. Escolha sua classe:",
        reply_markup=InlineKeyboardMarkup(botoes),
    )
    return CLASSE


async def receber_classe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    classe_id = int(query.data.split("_")[1])

    session = get_session()
    classe = session.get(Classe, classe_id)
    tg_id = str(update.effective_user.id)

    ja_existe = session.query(Player).filter_by(telegram_id=tg_id).first()
    if ja_existe:
        session.close()
        await query.edit_message_text(
            "Você já tem um personagem criado. Use /status pra ver a ficha."
        )
        return ConversationHandler.END

    from game.atributos import (
        calcular_hp_maximo, calcular_vigor_maximo, calcular_mana_maximo,
        calcular_critico_chance, resolver_item_do_kit, calcular_defesa_preview_classe,
    )
    from handlers.comercio import _icone_tipo
    from db.models import HabilidadeAtiva

    # 1. Resolução segura de itens do kit
    kit_linhas = []
    itens_resolvidos = []
    for parte in (classe.kit_inicial or "").split("+"):
        parte = parte.strip()
        res = resolver_item_do_kit(session, parte)
        if res:
            itens_resolvidos.append(res)
            icone = _icone_tipo(res["tipo_ou_slot"])
            q_txt = f"{res['qty']}x " if res["qty"] > 1 else ""
            kit_linhas.append(f"{icone} {q_txt}{res['nome']} — {res['tipo_stat']} {res['valor_stat']}")
    kit_texto = "\n".join(kit_linhas) if kit_linhas else (classe.kit_inicial or "")

    # 2. Status reais calculados no Nível 1
    hp_nv1 = calcular_hp_maximo(classe=classe, nivel=1, session=session)
    vig_nv1 = calcular_vigor_maximo(classe=classe)
    mana_nv1 = calcular_mana_maximo(classe=classe, nivel=1, session=session)
    def_nv1 = calcular_defesa_preview_classe(session, classe, itens_resolvidos)
    crit_nv1 = int(round(calcular_critico_chance(classe=classe)))

    # 3. Progressão por Nível
    hp_faixa, mana_faixa = calcular_faixa_progressao(classe)
    progressao_linhas = (
        f"📈 *Progressão por Nível:*\n"
        f"• HP: {hp_faixa} por nível | Mana: {mana_faixa} por nível\n"
        f"• Vigor e Defesa: Fixos (evoluem apenas via equipamentos)"
    )

    # 4. Habilidade Ativa de Rank 1
    hab = session.query(HabilidadeAtiva).filter_by(classe_id=classe.id).first()
    hab_bloco = ""
    if hab:
        desc_r1 = formatar_efeito_rank1(hab)
        nome_hab_esc = escape_markdown(hab.habilidade_nome, version=1)
        desc_r1_esc = escape_markdown(desc_r1, version=1)
        hab_bloco = (
            f"⚔️ Habilidade Ativa: *{nome_hab_esc}*\n"
            f"{desc_r1_esc}\n\n"
        )

    # 5. Passiva / Vantagem (unificada se cópia literal)
    duplicadas = ("Guerreiro da Forja", "Ladino das Sombras", "Bárbaro da Fenda")
    if classe.nome in duplicadas:
        vantagem_rotulo = "✨ *Passiva / Vantagem:*"
    else:
        vantagem_rotulo = "✨ *Vantagem:*"

    emoji_cls = classe.emoji or ICONE_CLASSE.get(classe.nome, "⚔️")
    nome_cls_esc = escape_markdown(classe.nome, version=1)
    papel_cls_esc = escape_markdown(classe.papel or "Combatente", version=1)
    historia_limpa = escape_markdown(classe.historia_origem or "", version=1).replace("\\_", " ")
    vantagem_esc = escape_markdown(classe.vantagem or "", version=1)
    desvantagem_esc = escape_markdown(classe.desvantagem or "", version=1)

    texto = (
        f"{emoji_cls} *{nome_cls_esc}* — {papel_cls_esc}\n\n"
        f"_{historia_limpa}_\n\n"
        f"📊 *Status no Nível 1:*\n"
        f"❤️ HP {hp_nv1}   🔷 Vigor {vig_nv1}\n"
        f"🔮 Mana {mana_nv1}   🛡️ Defesa {def_nv1}\n"
        f"🎯 Crítico {crit_nv1}%\n\n"
        f"{progressao_linhas}\n\n"
        f"🎒 *Kit Inicial:*\n{kit_texto}\n\n"
        f"{hab_bloco}"
        f"{vantagem_rotulo} {vantagem_esc}\n"
        f"❌ *Desvantagem:* {desvantagem_esc}"
    )
    session.close()
    await query.edit_message_text(
        texto, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"✅ Confirmar {classe.nome}", callback_data=f"confirmar_classe_{classe_id}")],
            [InlineKeyboardButton("⬅️ Ver outras classes", callback_data="voltar_classes")],
        ]),
    )
    return CLASSE


async def voltar_classes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    classes = session.query(Classe).all()
    botoes = [
        [InlineKeyboardButton(f"{c.emoji or ICONE_CLASSE.get(c.nome, '⚔️')} {c.nome}", callback_data=f"classe_{c.id}")]
        for c in classes
    ]
    session.close()
    await query.edit_message_text(
        f"Bem-vindo, {context.user_data['nome_personagem']}. Escolha sua classe:",
        reply_markup=InlineKeyboardMarkup(botoes),
    )
    return CLASSE


async def confirmar_criacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    classe_id = int(query.data.split("_")[-1])

    session = get_session()
    classe = session.get(Classe, classe_id)
    tg_id = str(update.effective_user.id)

    ja_existe = session.query(Player).filter_by(telegram_id=tg_id).first()
    if ja_existe:
        session.close()
        await query.edit_message_text(
            "Você já tem um personagem criado. Use /status pra ver a ficha."
        )
        return ConversationHandler.END

    curva_nv1 = session.query(CurvaMestra).filter_by(nivel=1).first()

    from game.atributos import calcular_hp_maximo, calcular_vigor_maximo, calcular_mana_maximo

    hp_max = calcular_hp_maximo(player=None, session=session, nivel=1, classe=classe)
    vig_max = calcular_vigor_maximo(player=None, classe=classe)
    mana_max = calcular_mana_maximo(nivel=1, classe=classe, session=session)

    novo_player = Player(
        telegram_id=tg_id,
        nome_personagem=context.user_data["nome_personagem"],
        classe_id=classe.id,
        nivel=1,
        xp_atual=0,
        hp_atual=hp_max,
        hp_max=hp_max,
        vig_atual=vig_max,
        vig_max=vig_max,
        mana_atual=mana_max,
        mana_max=mana_max,
        ouro=100,
    )
    from game.atributos import entregar_kit_inicial
    session.add(novo_player)
    session.flush()
    entregar_kit_inicial(session, novo_player, classe)
    session.commit()

    nome_classe = classe.nome
    vantagem = classe.vantagem
    desvantagem = classe.desvantagem
    session.close()

    await query.edit_message_text(
        f"✅ {context.user_data['nome_personagem']}, o {nome_classe}, está pronto.\n\n"
        f"*Vantagem:* {vantagem}\n"
        f"*Desvantagem:* {desvantagem}\n\n"
        "Digite /status pra ver sua ficha.",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


# ---------- HUD de status ----------
async def mostrar_hud(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    if not player:
        await update.message.reply_text("Você ainda não tem personagem. Use /start.")
        session.close()
        return

    from game.narrativa import checar_narracao_pendente, sincronizar_tier
    sincronizar_tier(session, player)
    narrativa_pendente = checar_narracao_pendente(session, player)
    if narrativa_pendente:
        session.commit()
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"📖 *{narrativa_pendente.titulo}*\n\n{narrativa_pendente.texto}",
            parse_mode="Markdown",
        )

    from game.login_diario import checar_e_aplicar_login
    resultado_login = checar_e_aplicar_login(session, player)
    if resultado_login:
        bonus, streak = resultado_login
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"🎁 *Login Diário!* Dia {streak} da sequência: +{bonus} Ouro",
            parse_mode="Markdown",
        )

    classe = session.get(Classe, player.classe_id) if player.classe_id else None
    nome_classe = classe.nome if classe else "Sem classe"

    from game.atributos import entregar_kit_inicial, calcular_mana_maximo
    entregar_kit_inicial(session, player, classe)

    mana_calc = calcular_mana_maximo(player=player, session=session, nivel=player.nivel)
    if not player.mana_max or player.mana_max < mana_calc:
        diff = mana_calc - (player.mana_max or 0)
        player.mana_max = mana_calc
        player.mana_atual = min(player.mana_max, (player.mana_atual or 0) + diff)
        session.commit()

    # protege contra personagem antigo com campo vazio (evita quebrar a barra)
    hp_max = player.hp_max or 24
    vig_max = player.vig_max or 60
    hp_atual = player.hp_atual if player.hp_atual is not None else hp_max
    vig_atual = player.vig_atual if player.vig_atual is not None else vig_max
    mana_max = player.mana_max or 0
    mana_atual = player.mana_atual if player.mana_atual is not None else mana_max
    xp_atual = player.xp_atual or 0
    curva = session.query(CurvaMestra).filter_by(nivel=player.nivel or 1).first()
    xp_prox = curva.xp_prox_nivel if curva else 20
    tier_atual = player.tier_mais_alto_alcancado or 1
    icone_classe = (classe.emoji if classe and classe.emoji else None) or ICONE_CLASSE.get(nome_classe, "🧍")

    from game.relogio import periodo_texto, ICONE_HORA, ICONE_CLIMA
    periodo = periodo_texto(player.hora_do_mundo or 8)
    clima = player.clima_atual or "Ensolarado"
    nome_escapado = (player.nome_personagem or "Aventureiro").replace("_", "\\_").replace("*", "\\*")
    titulo_txt = f", o {player.titulo_ativo}" if getattr(player, "titulo_ativo", None) else ""
    texto = (
        f"{icone_classe} *{nome_escapado}{titulo_txt}* — {nome_classe}\n"
        f"🎖️ Nível {player.nivel or 1}  ·  🏔️ Tier {tier_atual}\n"
        f"{ICONE_HORA[periodo]} {player.hora_do_mundo or 8}h ({periodo}) · {ICONE_CLIMA.get(clima,'☀️')} {clima}\n\n"
        f"❤️ HP: {hp_atual}/{hp_max}\n{barra(hp_atual, hp_max)}\n"
        f"⚡ Vigor: {vig_atual}/{vig_max}\n{barra(vig_atual, vig_max)}\n"
    )
    if mana_max:
        texto += f"🔷 Mana: {mana_atual}/{mana_max}\n{barra(mana_atual, mana_max, cheio='🟦')}\n"
    texto += (
        f"✨ XP: {xp_atual}/{xp_prox}\n{barra(xp_atual, xp_prox, cheio='🟨')}\n\n"
        f"💰 Ouro: {player.ouro or 0}"
    )

    from db.models import PlayerProficiencia
    from game.proficiencia import nivel_e_progresso
    proficiencias = session.query(PlayerProficiencia).filter_by(player_id=player.id).all()
    proficiencias_com_nivel = []
    for p in proficiencias:
        nivel, atual, proximo = nivel_e_progresso(p.valor)
        if nivel > 0:
            proficiencias_com_nivel.append((p.tipo_arma, nivel, atual, proximo))
    if proficiencias_com_nivel:
        texto += "\n\n🗡️ *Proficiência:*"
        for tipo_arma, nivel, atual, proximo in proficiencias_com_nivel:
            texto += f"\n{tipo_arma}: Nv.{nivel} ({atual}/{proximo})" if proximo else f"\n{tipo_arma}: Nv.{nivel} (MÁX)"
    corrupcao = player.corrupcao or 0
    if corrupcao > 0:
        estagio = min(5, corrupcao // 20 + 1)
        texto += f"\n\n👁️ Corrupção: {corrupcao}/100 (Estágio {estagio})"

    from game.talentos import obter_talentos_jogador
    talentos_aprendidos = obter_talentos_jogador(session, player)
    if talentos_aprendidos:
        texto += "\n\n🌟 *Talentos:*"
        for t_info in talentos_aprendidos:
            tag_label = f" ({t_info['tag']})" if t_info.get("tag") else ""
            texto += f"\n• *{t_info['nome']}* (Nv.{t_info['nivel']}){tag_label}"
    botoes = [
        [InlineKeyboardButton("⚔️ Aventura", callback_data="menu_aventura"),
         InlineKeyboardButton("🎒 Inventário", callback_data="menu_inventario")],
        [InlineKeyboardButton("🗺️ Mapa", callback_data="menu_mapa"),
         InlineKeyboardButton("🏪 Comércio", callback_data="menu_comercio")],
        [InlineKeyboardButton("📜 Missões", callback_data="menu_missoes"),
         InlineKeyboardButton("🏛️ Facções", callback_data="menu_faccoes")],
        [InlineKeyboardButton("📖 Codex", callback_data="menu_codex")],
    ]
    session.close()

    if update.callback_query:
        await update.callback_query.edit_message_text(
            texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes)
        )
    else:
        await update.message.reply_text(
            texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes)
        )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await mostrar_hud(update, context)


async def menu_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await mostrar_hud(update, context)


async def botao_em_construcao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🚧 Essa tela ainda não foi construída — chega numa próxima fase.", show_alert=True)


async def tratar_erro(update: object, context: ContextTypes.DEFAULT_TYPE):
    """
    Rede de segurança global: se qualquer tela quebrar, o jogador recebe um aviso
    em vez de o botão simplesmente não fazer nada. O erro completo continua indo
    pro log do Render pra eu conseguir diagnosticar.
    """
    log.error("Erro não tratado:", exc_info=context.error)
    if isinstance(update, Update):
        aviso = "⚠️ Algo deu errado nessa ação. O erro foi registrado. Use /status pra voltar."
        try:
            if update.callback_query:
                await update.callback_query.answer(aviso, show_alert=True)
            elif update.effective_message:
                await update.effective_message.reply_text(aviso)
        except Exception:
            pass


# ---------- "porteiro" HTTP: só existe pra o Render confirmar que o servico esta vivo ----------

class _Porteiro(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot rodando.")

    def log_message(self, *args):
        pass  # evita poluir o log com toda visita do checador do Render


def iniciar_porteiro():
    porta = int(os.getenv("PORT", "10000"))
    servidor = HTTPServer(("0.0.0.0", porta), _Porteiro)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    log.info(f"Porteiro HTTP escutando na porta {porta} (só pro Render, não é o jogo).")


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Defina TELEGRAM_BOT_TOKEN no .env antes de rodar.")

    log.info("Verificando dados do jogo...")
    importar_dados_do_jogo()

    iniciar_porteiro()

    persistence = PicklePersistence(filepath="bot_conversas.pickle")
    app = Application.builder().token(token).persistence(persistence).build()

    conv = ConversationHandler(
        name="criacao_personagem",
        persistent=True,
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("reset", reset_cmd),
            CallbackQueryHandler(reset_cmd, pattern=r"^reiniciar_jogo$"),
        ],
        states={
            NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome)],
            CLASSE: [
                CallbackQueryHandler(receber_classe, pattern=r"^classe_"),
                CallbackQueryHandler(confirmar_criacao, pattern=r"^confirmar_classe_"),
                CallbackQueryHandler(voltar_classes, pattern=r"^voltar_classes$"),
            ],
        },
        fallbacks=[
            CommandHandler("reset", reset_cmd),
            CallbackQueryHandler(reset_cmd, pattern=r"^reiniciar_jogo$"),
        ],
        allow_reentry=True,
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CallbackQueryHandler(reset_cmd, pattern=r"^reiniciar_jogo$"))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CallbackQueryHandler(menu_status_callback, pattern=r"^menu_status$"))
    app.add_handler(CallbackQueryHandler(menu_aventura, pattern=r"^menu_aventura$"))
    app.add_handler(CallbackQueryHandler(explorar, pattern=r"^explorar$"))
    app.add_handler(CallbackQueryHandler(descansar_handler, pattern=r"^descansar$"))
    app.add_handler(CallbackQueryHandler(atacar, pattern=r"^atacar$"))
    app.add_handler(CallbackQueryHandler(habilidade_ativa_fisica_handler, pattern=r"^hab_ativa_fisica$"))
    app.add_handler(CallbackQueryHandler(habilidade_ativa_magica_handler, pattern=r"^hab_ativa_magica$"))
    app.add_handler(CallbackQueryHandler(fugir, pattern=r"^fugir$"))
    app.add_handler(CallbackQueryHandler(menu_magias, pattern=r"^menu_magias$"))
    app.add_handler(CallbackQueryHandler(menu_comercio, pattern=r"^menu_comercio$"))
    app.add_handler(CallbackQueryHandler(menu_treinador, pattern=r"^menu_treinador$"))
    app.add_handler(CallbackQueryHandler(confirmar_upgrade_rank, pattern=r"^treinador_upar$"))
    app.add_handler(CallbackQueryHandler(listar_pocoes, pattern=r"^loja_pocoes$"))
    app.add_handler(CallbackQueryHandler(confirmar_compra_pocao, pattern=r"^pocao_comprar_"))
    app.add_handler(CallbackQueryHandler(listar_compra, pattern=r"^loja_comprar_(arma|armadura)(_.+)?$"))
    app.add_handler(CallbackQueryHandler(confirmar_compra, pattern=r"^loja_comprarid_"))
    app.add_handler(CallbackQueryHandler(listar_venda, pattern=r"^loja_vender$"))
    app.add_handler(CallbackQueryHandler(confirmar_venda, pattern=r"^loja_venderid_"))
    app.add_handler(CallbackQueryHandler(vender_tudo_callback, pattern=r"^loja_vender_tudo$"))
    app.add_handler(CallbackQueryHandler(menu_crafting, pattern=r"^loja_crafting(_\w+)?$"))
    app.add_handler(CallbackQueryHandler(confirmar_forja, pattern=r"^loja_forjar_"))
    app.add_handler(CallbackQueryHandler(confirmar_comprar_diagrama, pattern=r"^loja_comp_diag_"))
    app.add_handler(CallbackQueryHandler(menu_curandeiro, pattern=r"^menu_curandeiro$"))
    app.add_handler(CallbackQueryHandler(curar_hp_curandeiro, pattern=r"^curandeiro_curar_hp$"))
    app.add_handler(CallbackQueryHandler(tratar_ferimento_curandeiro, pattern=r"^curandeiro_tratar_ferimento$"))
    app.add_handler(CallbackQueryHandler(purificar_curandeiro, pattern=r"^curandeiro_purificar$"))
    app.add_handler(CallbackQueryHandler(purificar_ficha_handler, pattern=r"^purificar_ficha$"))
    app.add_handler(CallbackQueryHandler(menu_inventario, pattern=r"^menu_inventario$"))
    app.add_handler(CallbackQueryHandler(painel_perfil, pattern=r"^painel_perfil$"))
    app.add_handler(CallbackQueryHandler(painel_equipamentos, pattern=r"^painel_equip$"))
    app.add_handler(CallbackQueryHandler(painel_mochila, pattern=r"^painel_mochila$"))
    app.add_handler(CallbackQueryHandler(painel_materiais, pattern=r"^painel_materiais$"))
    app.add_handler(CallbackQueryHandler(consumir_material_mutacao, pattern=r"^consumir_mat_\d+$"))
    app.add_handler(CallbackQueryHandler(painel_grimorio, pattern=r"^painel_grimorio$"))
    app.add_handler(CallbackQueryHandler(alternar_equipar, pattern=r"^inv_(equipar|desequipar)_"))
    app.add_handler(CallbackQueryHandler(usar_consumivel, pattern=r"^inv_usar_"))
    app.add_handler(CallbackQueryHandler(descartar_item, pattern=r"^inv_descartar_"))
    app.add_handler(CallbackQueryHandler(lootear, pattern=r"^lootear$"))
    app.add_handler(CallbackQueryHandler(poupar, pattern=r"^poupar$"))
    app.add_handler(CallbackQueryHandler(menu_missoes, pattern=r"^menu_missoes(_.+)?$"))
    app.add_handler(CallbackQueryHandler(cb_aceitar_missao, pattern=r"^miss_aceitar_"))
    app.add_handler(CallbackQueryHandler(cb_entregar_missao, pattern=r"^miss_entregar_"))
    app.add_handler(CallbackQueryHandler(cb_reroll_missao, pattern=r"^miss_reroll_"))
    app.add_handler(CallbackQueryHandler(cb_missao_bloqueada, pattern=r"^miss_bloqueada_"))
    app.add_handler(CallbackQueryHandler(menu_faccoes, pattern=r"^menu_faccoes(_.+)?$"))
    app.add_handler(CallbackQueryHandler(menu_titulos, pattern=r"^menu_titulos$"))
    app.add_handler(CallbackQueryHandler(cb_equipar_titulo, pattern=r"^titulo_equipar_\d+$"))
    app.add_handler(CallbackQueryHandler(menu_codex, pattern=r"^menu_codex$"))
    app.add_handler(CallbackQueryHandler(codex_bestiario_tiers, pattern=r"^codex_bestiario$"))
    app.add_handler(CallbackQueryHandler(codex_bestiario_lista, pattern=r"^codex_bestiario_\d+$"))
    app.add_handler(CallbackQueryHandler(codex_monstro_detalhe, pattern=r"^codex_monstro_"))
    app.add_handler(CallbackQueryHandler(codex_locais, pattern=r"^codex_locais$"))
    app.add_handler(CallbackQueryHandler(codex_materiais, pattern=r"^codex_materiais$"))
    app.add_handler(CallbackQueryHandler(menu_mapa, pattern=r"^menu_mapa$"))
    app.add_handler(CallbackQueryHandler(mapa_regional, pattern=r"^mapa_regional$"))
    app.add_handler(CallbackQueryHandler(mapa_global, pattern=r"^mapa_global$"))
    app.add_handler(CallbackQueryHandler(mapa_atravessar_portao, pattern=r"^mapa_portao$"))
    app.add_handler(CallbackQueryHandler(mapa_ir_cidade, pattern=r"^mapa_ir_cidade_\d+$"))
    app.add_handler(CallbackQueryHandler(viajar_local, pattern=r"^mapa_ir_\d+$"))
    app.add_handler(CallbackQueryHandler(conjurar, pattern=r"^magia_\d+$"))
    app.add_handler(CallbackQueryHandler(voltar_combate, pattern=r"^voltar_combate$"))
    app.add_handler(CallbackQueryHandler(botao_em_construcao, pattern=r"^menu_"))
    app.add_error_handler(tratar_erro)

    log.info("Bot iniciado.")
    app.run_polling()


if __name__ == "__main__":
    main()
