"""
Fase 4 — Inventário: ver itens, equipar/desequipar.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from db.connection import get_session
from db.models import Player, PlayerInventario, Arma, Armadura

ICONE_TIPO = {
    "arma": "⚔️", "armadura": "🛡️", "material": "🧱",
    "consumivel": "🧪", "ferramenta": "🔨", "acessorio": "💍",
    "arma_armadura_forjada": "🔧",
}


async def menu_inventario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()
    itens = session.query(PlayerInventario).filter_by(player_id=player.id).all()

    equipaveis = [i for i in itens if i.tipo_item in ("arma", "armadura", "acessorio")]
    outros = [i for i in itens if i.tipo_item not in ("arma", "armadura", "acessorio")]

    texto = "🎒 *Inventário*\n\n"
    botoes = []

    if equipaveis:
        from handlers.comercio import _icone_tipo
        from db.models import Arma, Armadura, Receita
        texto += "*Equipamento:*\n"
        for i in equipaveis:
            marca = "✅ " if i.equipado else ""
            item_real = None
            stat_txt = ""
            icone_item = None
            if i.tipo_item == "arma" and i.item_ref_id:
                item_real = session.query(Arma).filter_by(id=i.item_ref_id).first()
                if item_real:
                    stat_txt = f" — ⚔️ Dano {item_real.dano_comum}"
            elif i.tipo_item == "armadura" and i.item_ref_id:
                item_real = session.query(Armadura).filter_by(id=i.item_ref_id).first()
                if item_real:
                    stat_txt = f" — 🛡️ Defesa {item_real.defesa_comum}"
            elif i.tipo_item == "acessorio":
                primeira_palavra = i.nome_item.split(" ")[0]
                icone_item = _icone_tipo(primeira_palavra)
                receita = session.query(Receita).filter_by(id=i.item_ref_id).first() if i.item_ref_id else None
                if receita and receita.efeito:
                    stat_txt = f" — _{receita.efeito}_"
            if icone_item is None:
                tipo_especifico = (item_real.tipo if i.tipo_item == "arma" else item_real.slot) if item_real else None
                icone_item = _icone_tipo(tipo_especifico) if tipo_especifico else ICONE_TIPO.get(i.tipo_item, "❔")
            texto += f"{icone_item} {marca}{i.nome_item}{stat_txt}\n"
            acao = "desequipar" if i.equipado else "equipar"
            botoes.append([InlineKeyboardButton(
                f"{'Desequipar' if i.equipado else 'Equipar'} {i.nome_item}",
                callback_data=f"inv_{acao}_{i.id}",
            )])

    if outros:
        texto += "\n*Materiais e Itens:*\n"
        for i in outros:
            texto += f"{ICONE_TIPO.get(i.tipo_item,'❔')} {i.nome_item} x{i.quantidade}\n"

    if not itens:
        texto += "Vazio. Vá pra Aventura ou Comércio pra conseguir itens."

    botoes.append([InlineKeyboardButton("⬅️ Voltar", callback_data="menu_status")])
    session.close()
    await query.edit_message_text(texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botoes))


async def alternar_equipar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, acao, inv_id = query.data.split("_")
    session = get_session()
    tg_id = str(update.effective_user.id)
    player = session.query(Player).filter_by(telegram_id=tg_id).first()

    item = session.query(PlayerInventario).filter_by(id=int(inv_id), player_id=player.id).first()
    if not item:
        await query.answer("Item não encontrado.", show_alert=True)
        session.close()
        return

    await query.answer()

    if acao == "equipar":
        # desequipa outro item do mesmo tipo (so 1 arma e 1 armadura por vez, regra simples)
        outros_equipados = (
            session.query(PlayerInventario)
            .filter_by(player_id=player.id, tipo_item=item.tipo_item, equipado=True)
            .all()
        )
        for o in outros_equipados:
            o.equipado = False
        item.equipado = True
    else:
        item.equipado = False

    session.commit()
    session.close()
    await menu_inventario(update, context)
