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
    ContextTypes, ConversationHandler, filters,
)
from dotenv import load_dotenv

from db.connection import get_session
from db.models import Player, Classe, CurvaMestra, Narrativa
from db.import_data import importar as importar_dados_do_jogo
from game.ui_utils import barra
from handlers.aventura import menu_aventura, explorar, atacar, fugir, voltar_combate, lootear, poupar
from handlers.magias import menu_magias, conjurar
from handlers.comercio import (
    menu_comercio, listar_compra, confirmar_compra, listar_venda, confirmar_venda,
    menu_crafting, confirmar_forja,
)
from handlers.inventario import menu_inventario, alternar_equipar
from handlers.missoes import menu_missoes, cb_aceitar_missao, cb_entregar_missao, menu_faccoes, menu_titulos
from handlers.mapa import menu_mapa, viajar_local
from handlers.codex import (
    menu_codex, codex_bestiario_tiers, codex_bestiario_lista, codex_monstro_detalhe,
    codex_locais, codex_materiais,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

NOME, CLASSE = range(2)


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


async def receber_nome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["nome_personagem"] = update.message.text.strip()

    session = get_session()
    classes = session.query(Classe).all()
    botoes = [
        [InlineKeyboardButton(c.nome, callback_data=f"classe_{c.id}")]
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

    curva_nv1 = session.query(CurvaMestra).filter_by(nivel=1).first()

    # status iniciais: usa a Curva Mestra nivel 1 como base
    hp_max = curva_nv1.hp if curva_nv1 else 24
    mana_max = curva_nv1.mana if curva_nv1 and curva_nv1.mana else 15
    vig_max = 60  # 60 + (CON-3)*10, CON=3 por padrão até a ficha de atributos existir

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
        tier_mais_alto_alcancado=1,
    )
    from game.atributos import aplicar_atributos_iniciais
    aplicar_atributos_iniciais(novo_player, classe)
    session.add(novo_player)
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

ICONE_CLASSE = {
    "Guerreiro da Forja": "🛡️", "Inquisidor de Prata": "✨", "Conjurador de Sangue (Hemomante)": "🩸",
    "Batedor dos Ecos": "🏹", "Ladino das Sombras": "🗡️", "Mago Elemental": "🔮",
    "Bárbaro da Fenda": "🪓", "Artífice Mecânico": "⚙️",
}


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

    from game.atributos import player_precisa_de_atributos, aplicar_atributos_iniciais
    if player_precisa_de_atributos(player):
        aplicar_atributos_iniciais(player, classe)
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
    icone_classe = ICONE_CLASSE.get(nome_classe, "🧍")

    texto = (
        f"{icone_classe} *{player.nome_personagem}* — {nome_classe}\n"
        f"🎖️ Nível {player.nivel or 1}  ·  🏔️ Tier {tier_atual}\n\n"
        f"❤️ HP: {hp_atual}/{hp_max}\n{barra(hp_atual, hp_max)}\n"
        f"⚡ Vigor: {vig_atual}/{vig_max}\n{barra(vig_atual, vig_max)}\n"
    )
    if mana_max:
        texto += f"🔷 Mana: {mana_atual}/{mana_max}\n{barra(mana_atual, mana_max, cheio='🟦')}\n"
    texto += (
        f"✨ XP: {xp_atual}/{xp_prox}\n{barra(xp_atual, xp_prox, cheio='🟨')}\n\n"
        f"💪 FOR: {player.atributo_for}   🏃 DES: {player.atributo_des}   🛡️ CON: {player.atributo_con}\n"
        f"🧠 INT: {player.atributo_int}   🦉 SAB: {player.atributo_sab}   💬 CAR: {player.atributo_car}\n\n"
        f"💰 Ouro: {player.ouro or 0}"
    )
    corrupcao = player.corrupcao or 0
    if corrupcao > 0:
        estagio = min(5, corrupcao // 20 + 1)
        texto += f"\n\n👁️ Corrupção: {corrupcao}/100 (Estágio {estagio})"
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

    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            NOME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receber_nome)],
            CLASSE: [CallbackQueryHandler(receber_classe, pattern=r"^classe_")],
        },
        fallbacks=[],
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CallbackQueryHandler(menu_status_callback, pattern=r"^menu_status$"))
    app.add_handler(CallbackQueryHandler(menu_aventura, pattern=r"^menu_aventura$"))
    app.add_handler(CallbackQueryHandler(explorar, pattern=r"^explorar$"))
    app.add_handler(CallbackQueryHandler(atacar, pattern=r"^atacar$"))
    app.add_handler(CallbackQueryHandler(fugir, pattern=r"^fugir$"))
    app.add_handler(CallbackQueryHandler(menu_magias, pattern=r"^menu_magias$"))
    app.add_handler(CallbackQueryHandler(menu_comercio, pattern=r"^menu_comercio$"))
    app.add_handler(CallbackQueryHandler(listar_compra, pattern=r"^loja_comprar_(arma|armadura)(_.+)?$"))
    app.add_handler(CallbackQueryHandler(confirmar_compra, pattern=r"^loja_comprarid_"))
    app.add_handler(CallbackQueryHandler(listar_venda, pattern=r"^loja_vender$"))
    app.add_handler(CallbackQueryHandler(confirmar_venda, pattern=r"^loja_venderid_"))
    app.add_handler(CallbackQueryHandler(menu_crafting, pattern=r"^loja_crafting(_\w+)?$"))
    app.add_handler(CallbackQueryHandler(confirmar_forja, pattern=r"^loja_forjar_"))
    app.add_handler(CallbackQueryHandler(menu_inventario, pattern=r"^menu_inventario$"))
    app.add_handler(CallbackQueryHandler(alternar_equipar, pattern=r"^inv_(equipar|desequipar)_"))
    app.add_handler(CallbackQueryHandler(lootear, pattern=r"^lootear$"))
    app.add_handler(CallbackQueryHandler(poupar, pattern=r"^poupar$"))
    app.add_handler(CallbackQueryHandler(menu_missoes, pattern=r"^menu_missoes(_.+)?$"))
    app.add_handler(CallbackQueryHandler(cb_aceitar_missao, pattern=r"^miss_aceitar_"))
    app.add_handler(CallbackQueryHandler(cb_entregar_missao, pattern=r"^miss_entregar_"))
    app.add_handler(CallbackQueryHandler(menu_faccoes, pattern=r"^menu_faccoes(_.+)?$"))
    app.add_handler(CallbackQueryHandler(menu_titulos, pattern=r"^menu_titulos$"))
    app.add_handler(CallbackQueryHandler(menu_codex, pattern=r"^menu_codex$"))
    app.add_handler(CallbackQueryHandler(codex_bestiario_tiers, pattern=r"^codex_bestiario$"))
    app.add_handler(CallbackQueryHandler(codex_bestiario_lista, pattern=r"^codex_bestiario_\d+$"))
    app.add_handler(CallbackQueryHandler(codex_monstro_detalhe, pattern=r"^codex_monstro_"))
    app.add_handler(CallbackQueryHandler(codex_locais, pattern=r"^codex_locais$"))
    app.add_handler(CallbackQueryHandler(codex_materiais, pattern=r"^codex_materiais$"))
    app.add_handler(CallbackQueryHandler(menu_mapa, pattern=r"^menu_mapa$"))
    app.add_handler(CallbackQueryHandler(viajar_local, pattern=r"^mapa_ir_"))
    app.add_handler(CallbackQueryHandler(conjurar, pattern=r"^magia_\d+$"))
    app.add_handler(CallbackQueryHandler(voltar_combate, pattern=r"^voltar_combate$"))
    app.add_handler(CallbackQueryHandler(botao_em_construcao, pattern=r"^menu_"))
    app.add_error_handler(tratar_erro)

    log.info("Bot iniciado.")
    app.run_polling()


if __name__ == "__main__":
    main()
