"""
A Infecção que Segura o Mundo — bot de Telegram
Fase 1: criação de personagem + HUD de status.
"""
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, ConversationHandler, filters,
)
from dotenv import load_dotenv

from db.connection import get_session
from db.models import Player, Classe, CurvaMestra
from db.import_data import importar as importar_dados_do_jogo

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

def barra(atual, maximo, tamanho=10):
    cheio = round(tamanho * max(0, min(atual, maximo)) / maximo) if maximo else 0
    return "🟩" * cheio + "⬛" * (tamanho - cheio)


async def mostrar_hud(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    if not player:
        await update.message.reply_text("Você ainda não tem personagem. Use /start.")
        session.close()
        return

    classe = session.get(Classe, player.classe_id)
    texto = (
        f"🧍 *{player.nome_personagem}* — {classe.nome}, Nv. {player.nivel}\n\n"
        f"❤️ HP: {player.hp_atual}/{player.hp_max}\n{barra(player.hp_atual, player.hp_max)}\n\n"
        f"⚡ Vigor: {player.vig_atual}/{player.vig_max}\n{barra(player.vig_atual, player.vig_max)}\n\n"
        f"✨ XP: {player.xp_atual}\n"
        f"💰 Ouro: {player.ouro}"
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


async def botao_em_construcao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🚧 Essa tela ainda não foi construída — chega na Fase 3.", show_alert=True)


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Defina TELEGRAM_BOT_TOKEN no .env antes de rodar.")

    log.info("Verificando dados do jogo...")
    importar_dados_do_jogo()

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
    app.add_handler(CallbackQueryHandler(botao_em_construcao, pattern=r"^menu_"))

    log.info("Bot iniciado.")
    app.run_polling()


if __name__ == "__main__":
    main()
