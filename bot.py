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
from db.models import Player, Classe, CurvaMestra
from db.import_data import importar as importar_dados_do_jogo
from handlers.aventura import menu_aventura, explorar, atacar, fugir

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

    await update.message.reply_text(
        "🌍 *A Infecção que Segura o Mundo*\n\n"
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

def barra(atual, maximo, tamanho=10, cheio="🟩"):
    cheio_n = round(tamanho * max(0, min(atual, maximo)) / maximo) if maximo else 0
    return cheio * cheio_n + "⬛" * (tamanho - cheio_n)


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

    classe = session.get(Classe, player.classe_id) if player.classe_id else None
    nome_classe = classe.nome if classe else "Sem classe"

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
        f"❤️ HP: {hp_atual}/{hp_max}\n{barra(hp_atual, hp_max)}\n\n"
        f"⚡ Vigor: {vig_atual}/{vig_max}\n{barra(vig_atual, vig_max)}\n\n"
    )
    if mana_max:
        texto += f"🔷 Mana: {mana_atual}/{mana_max}\n{barra(mana_atual, mana_max, cheio='🟦')}\n\n"
    texto += (
        f"✨ XP: {xp_atual}/{xp_prox}\n{barra(xp_atual, xp_prox, cheio='🟨')}\n\n"
        f"💰 Ouro: {player.ouro or 0}"
    )
    botoes = [
        [InlineKeyboardButton("⚔️ Aventura", callback_data="menu_aventura"),
         InlineKeyboardButton("🎒 Inventário", callback_data="menu_inventario")],
        [InlineKeyboardButton("🗺️ Mapa", callback_data="menu_mapa"),
         InlineKeyboardButton("🏪 Comércio", callback_data="menu_comercio")],
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
    app.add_handler(CallbackQueryHandler(botao_em_construcao, pattern=r"^menu_"))
    app.add_error_handler(tratar_erro)

    log.info("Bot iniciado.")
    app.run_polling()


if __name__ == "__main__":
    main()
