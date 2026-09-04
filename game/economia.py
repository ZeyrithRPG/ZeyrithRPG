"""
Fase 3 — Economia: comprar/vender equipamento, forjar receitas.
Logica pura (sem Telegram aqui) -- so mexe no banco via Session.
"""
import re
from db.models import Arma, Armadura, Receita, PlayerInventario


class ErroEconomia(Exception):
    pass


def _parse_qtd(texto_material):
    """'Sucata Retorcida (3x)' -> ('Sucata Retorcida', 3). Sem parenteses = 1x."""
    if not texto_material:
        return None, 0
    m = re.match(r"^(.*?)\s*\((\d+)x?\)\s*$", texto_material.strip())
    if m:
        return m.group(1).strip(), int(m.group(2))
    return texto_material.strip(), 1


def listar_equipamento(session, tier_nome, categoria):
    """categoria: 'arma' ou 'armadura'."""
    Modelo = Arma if categoria == "arma" else Armadura
    return session.query(Modelo).filter_by(tier=tier_nome).all()


def comprar_item(session, player, item_ref_id, categoria):
    Modelo = Arma if categoria == "arma" else Armadura
    item = session.query(Modelo).filter_by(id=item_ref_id).first()
    if not item:
        raise ErroEconomia("Item não encontrado.")
    if player.ouro < item.preco_compra:
        raise ErroEconomia(f"Ouro insuficiente. Precisa de {item.preco_compra}, tem {player.ouro}.")
    player.ouro -= item.preco_compra
    inv = PlayerInventario(
        player_id=player.id, tipo_item=categoria, item_ref_id=item.id,
        nome_item=item.variacao, quantidade=1, equipado=False,
    )
    session.add(inv)
    session.commit()
    return inv


def vender_item(session, player, inventario_id):
    inv = session.query(PlayerInventario).filter_by(id=inventario_id, player_id=player.id).first()
    if not inv:
        raise ErroEconomia("Você não tem esse item.")
    if inv.tipo_item not in ("arma", "armadura"):
        raise ErroEconomia("Esse tipo de item não pode ser vendido aqui.")
    Modelo = Arma if inv.tipo_item == "arma" else Armadura
    item_ref = session.query(Modelo).filter_by(id=inv.item_ref_id).first()
    preco = item_ref.preco_venda_mercador if item_ref else 0
    player.ouro += preco
    if inv.quantidade > 1:
        inv.quantidade -= 1
    else:
        session.delete(inv)
    session.commit()
    return preco


def listar_receitas(session, tier_nome):
    return session.query(Receita).filter_by(tier=tier_nome).all()


def _tem_material(session, player, nome_material, qtd_necessaria):
    inv = (
        session.query(PlayerInventario)
        .filter_by(player_id=player.id, tipo_item="material", nome_item=nome_material)
        .first()
    )
    return inv, (inv.quantidade if inv else 0) >= qtd_necessaria


def verificar_forja(session, player, receita_id):
    """Retorna (pode_forjar: bool, motivo: str, materiais_necessarios: list)."""
    receita = session.query(Receita).filter_by(id=receita_id).first()
    if not receita:
        return False, "Receita não encontrada.", []

    necessarios = []
    for campo in (receita.material_base_1, receita.material_base_2):
        nome, qtd = _parse_qtd(campo)
        if nome:
            necessarios.append((nome, qtd))

    faltando = []
    for nome, qtd in necessarios:
        _, tem = _tem_material(session, player, nome, qtd)
        if not tem:
            faltando.append(f"{nome} ({qtd}x)")

    custo = receita.custo_base_ouro or 0
    if player.ouro < custo:
        faltando.append(f"{custo} Ouro (você tem {player.ouro})")

    if faltando:
        return False, "Faltando: " + ", ".join(faltando), necessarios
    return True, "", necessarios


def forjar_item(session, player, receita_id):
    pode, motivo, necessarios = verificar_forja(session, player, receita_id)
    if not pode:
        raise ErroEconomia(motivo)

    receita = session.query(Receita).filter_by(id=receita_id).first()

    for nome, qtd in necessarios:
        inv, _ = _tem_material(session, player, nome, qtd)
        if inv.quantidade > qtd:
            inv.quantidade -= qtd
        else:
            session.delete(inv)

    player.ouro -= (receita.custo_base_ouro or 0)

    novo = PlayerInventario(
        player_id=player.id,
        tipo_item="acessorio" if receita.categoria == "Acessório" else "arma_armadura_forjada",
        item_ref_id=receita.id, nome_item=receita.tipo_slot, quantidade=1, equipado=False,
    )
    session.add(novo)
    session.commit()
    return novo
