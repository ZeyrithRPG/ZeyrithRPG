"""
Fase 4 — Loot: XP, Ouro e materiais reais ao vencer combate.
Antes disso o jogo dava XP/Ouro generico e nunca soltava material nenhum.
"""
import random
import re

FATOR_XP = {"Comum": 0.12, "Elite": 0.35, "Boss": 1.0, "Cosmico": 2.5}
MULT_OURO = {"Comum": 1.0, "Elite": 2.5, "Boss": 8.0, "Cosmico": 15.0}
OURO_POR_HP = 0.3

CHANCE_PADRAO_POR_RARIDADE = {
    "Comum": 0.70, "Incomum": 0.35, "Raro": 0.12, "Exclusivo": 1.0,
}


def calcular_xp(curva_mestra_jogador, papel_monstro):
    if not curva_mestra_jogador:
        return 5
    fator = FATOR_XP.get(papel_monstro, 0.12)
    return max(1, round(curva_mestra_jogador.xp_prox_nivel * fator))


def calcular_ouro(hp_monstro, papel_monstro):
    mult = MULT_OURO.get(papel_monstro, 1.0)
    return max(1, round((hp_monstro or 10) * OURO_POR_HP * mult))


def _parse_materiais(texto_materiais_dropados):
    """
    'Ouro + Couro Áspero de Javali (chance rara) + Presa Sanguínea (exclusivo)'
    -> [('Couro Áspero de Javali', 'rara'), ('Presa Sanguínea', 'exclusivo')]
    (ignora 'Ouro', que é tratado separado)
    """
    if not texto_materiais_dropados:
        return []
    partes = [p.strip() for p in texto_materiais_dropados.split("+")]
    out = []
    for p in partes:
        if not p or p.lower() == "ouro":
            continue
        m = re.match(r"^(.*?)\s*\((.*?)\)\s*$", p)
        if m:
            out.append((m.group(1).strip(), m.group(2).strip().lower()))
        else:
            out.append((p, None))
    return out


def rolar_materiais(session, texto_materiais_dropados):
    """Retorna lista de (nome_material, quantidade) que efetivamente dropou."""
    from db.models import Material

    materiais = _parse_materiais(texto_materiais_dropados)
    dropados = []
    for nome, anotacao in materiais:
        if anotacao and "exclusivo" in anotacao:
            chance = 1.0
        elif anotacao and "rara" in anotacao:
            chance = 0.10
        elif anotacao and "incomum" in anotacao:
            chance = 0.35
        else:
            ref = session.query(Material).filter_by(nome=nome).first()
            raridade_texto = (ref.raridade or "") if ref else ""
            chave = raridade_texto.split(" ")[0] if raridade_texto else "Comum"
            chance = CHANCE_PADRAO_POR_RARIDADE.get(chave, 0.5)

        if random.random() <= chance:
            dropados.append((nome, 1))
    return dropados


def resolver_loot(session, player, monstro, curva_mestra_jogador):
    """Calcula tudo de uma vez: XP, Ouro, materiais. NAO aplica no banco ainda --
    isso e feito por quem chama, junto com o resto da logica de vitoria."""
    xp = calcular_xp(curva_mestra_jogador, monstro.papel)
    ouro = calcular_ouro(monstro.hp, monstro.papel)
    materiais = rolar_materiais(session, monstro.materiais_dropados)
    return xp, ouro, materiais


def aplicar_loot_no_inventario(session, player, materiais_dropados):
    from db.models import PlayerInventario

    for nome, qtd in materiais_dropados:
        existente = (
            session.query(PlayerInventario)
            .filter_by(player_id=player.id, tipo_item="material", nome_item=nome)
            .first()
        )
        if existente:
            existente.quantidade += qtd
        else:
            session.add(PlayerInventario(
                player_id=player.id, tipo_item="material", nome_item=nome, quantidade=qtd,
            ))
