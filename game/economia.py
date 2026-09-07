"""
Fase 3 — Economia: comprar/vender equipamento, forjar receitas.
Logica pura (sem Telegram aqui) -- so mexe no banco via Session.
"""
import re
from db.models import Arma, Armadura, Receita, PlayerInventario, PlayerReceita


import unicodedata


class ErroEconomia(Exception):
    pass


def _normalizar(texto):
    """Remove acento pra comparar nomes que vieram de abas diferentes da planilha
    e podem ter sido digitados com/sem acento (ex: 'Maça' vs 'Maca')."""
    if not texto:
        return texto
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def _parse_qtd(texto_material):
    """
    Suporta:
    - 'Sucata Retorcida (3x)' -> ('Sucata Retorcida', 3)
    - '2x Sucata de Ferro' -> ('Sucata de Ferro', 2)
    - 'Sucata Retorcida' -> ('Sucata Retorcida', 1)
    """
    if not texto_material:
        return None, 0
    txt = texto_material.strip()
    m_pref = re.match(r"^(\d+)x\s+(.*?)$", txt, re.IGNORECASE)
    if m_pref:
        return m_pref.group(2).strip(), int(m_pref.group(1))
    m_suf = re.match(r"^(.*?)\s*\((\d+)x?\)\s*$", txt)
    if m_suf:
        return m_suf.group(1).strip(), int(m_suf.group(2))
    return txt, 1


def obter_materiais_receita(receita):
    """Extrai lista de (nome_material, quantidade) da receita, tratando múltiplos materiais com '+'."""
    necessarios = []
    for campo in (receita.material_base_1, receita.material_base_2):
        if not campo:
            continue
        subcampos = [s.strip() for s in campo.split("+")] if "+" in campo else [campo]
        for sub in subcampos:
            nome, qtd = _parse_qtd(sub)
            if nome:
                necessarios.append((nome, qtd))
    return necessarios


def slots_mochila_ocupados(session, player) -> int:
    """Calcula quantidade de vagas ocupadas na mochila (itens não-materiais e desequipados)."""
    itens = (
        session.query(PlayerInventario)
        .filter(
            PlayerInventario.player_id == player.id,
            PlayerInventario.tipo_item != "material",
            PlayerInventario.equipado == False,  # noqa: E712
        )
        .all()
    )
    return sum(i.quantidade or 1 for i in itens)


def listar_equipamento(session, tier_nome, categoria):
    """categoria: 'arma' ou 'armadura'."""
    Modelo = Arma if categoria == "arma" else Armadura
    return session.query(Modelo).filter_by(tier=tier_nome).all()


def comprar_item(session, player, arg1, arg2):
    if isinstance(arg1, int) or (isinstance(arg1, str) and arg1.isdigit()):
        item_ref_id = int(arg1)
        categoria = str(arg2)
    else:
        categoria = str(arg1)
        item_ref_id = int(arg2)

    Modelo = Arma if categoria == "arma" else Armadura
    item = session.query(Modelo).filter_by(id=item_ref_id).first()
    if not item:
        raise ErroEconomia("Item não encontrado.")

    max_vagas = player.slots_mochila_max or 20
    if slots_mochila_ocupados(session, player) >= max_vagas:
        raise ErroEconomia(f"Mochila cheia! Limite de {max_vagas} vagas atingido. Venda ou descarte itens primeiro.")

    preco_final = calcular_preco_compra_item(player, item, categoria)
    if player.ouro < preco_final:
        raise ErroEconomia(f"Ouro insuficiente. Precisa de {preco_final}, tem {player.ouro}.")

    player.ouro -= preco_final
    inv = PlayerInventario(
        player_id=player.id, tipo_item=categoria, item_ref_id=item.id,
        nome_item=item.variacao, quantidade=1, equipado=False,
    )
    session.add(inv)
    session.commit()
    return inv


def calcular_preco_compra_item(player, item, categoria: str) -> int:
    """
    Calcula o preço final de compra de um equipamento aplicando modificadores:
    - Estágios 4 e 5 de Corrupção (Hospedeiro / Ponto de Não Retorno): +20% nos preços
    - Mutação 8 (Mandíbula de Fera): +5% de preço de compra
    - Mutação 6 (Voz Dupla dos Ecos): -5% de desconto de loja
    - Mutação 13 (Asas Atrofiadas de Morcego): +50% no preço de armaduras
    """
    base = item.preco_compra if item and hasattr(item, "preco_compra") else 10
    mult = 1.0

    if player:
        from game.corrupcao import estagio_corrupcao
        corr = getattr(player, "corrupcao", 0) or 0
        est = estagio_corrupcao(corr)
        if est in (4, 5):
            mult += 0.20

        try:
            mutacoes = getattr(player, "mutacoes", None)
            if mutacoes:
                for m in mutacoes:
                    mid = getattr(m, "mutacao_id", 0)
                    if mid == 8:
                        mult += 0.05
                    elif mid == 6:
                        mult -= 0.05
                    elif mid == 13 and categoria == "armadura":
                        mult += 0.50
        except Exception:
            pass

    return max(1, round(base * mult))


def calcular_custo_reparo(player, item_inv, arma_ou_armadura_ref=None, proficiencia_nivel: int = 0) -> int:
    """
    Calcula o custo em ouro para reparar um item danificado:
    - Base de reparo: 25% do valor de compra do item (mínimo 5).
    - Descontos cumulativos:
      * Artífice Mecânico: -30%
      * Título Ativo 'Ferreiro de Mão Cheia': -10%
      * Proficiência com a arma: -2% a cada 6 níveis (até -10% no nível 30)
      * Mutação 13 (Asas Atrofiadas): +50% se for armadura
    """
    preco_base = 20
    if arma_ou_armadura_ref and hasattr(arma_ou_armadura_ref, "preco_compra"):
        preco_base = arma_ou_armadura_ref.preco_compra
    elif item_inv and getattr(item_inv, "item_ref_id", None):
        try:
            from db.connection import get_session
            from db.models import Arma, Armadura
            from sqlalchemy.orm import object_session
            sess = object_session(item_inv)
            if sess:
                if item_inv.tipo_item == "arma":
                    ref = sess.query(Arma).filter_by(id=item_inv.item_ref_id).first()
                else:
                    ref = sess.query(Armadura).filter_by(id=item_inv.item_ref_id).first()
                if ref and ref.preco_compra:
                    preco_base = ref.preco_compra
        except Exception:
            pass

    base_reparo = max(5, int(round(preco_base * 0.25)))

    desconto = 0.0
    if player:
        cls = getattr(player, "classe", None)
        cls_nome = cls.nome if cls else ""
        if "Artífice" in cls_nome or "Artifice" in cls_nome:
            desconto += 0.30

        if getattr(player, "titulo_ativo", None) == "Ferreiro de Mão Cheia":
            desconto += 0.10

    if proficiencia_nivel and proficiencia_nivel > 0:
        desconto += (min(30, max(0, proficiencia_nivel)) // 6) * 0.02

    mult = max(0.20, 1.0 - desconto)

    if player and getattr(item_inv, "tipo_item", "") == "armadura":
        try:
            mutacoes = getattr(player, "mutacoes", None)
            if mutacoes and any(getattr(m, "mutacao_id", 0) == 13 for m in mutacoes):
                mult += 0.50
        except Exception:
            pass

    return max(1, int(round(base_reparo * mult)))


def reparar_item(session, player, inventario_id: int, proficiencia_nivel: int = 0) -> tuple[bool, str, int]:
    """
    Repara um item do inventário do jogador, debitando o ouro e incrementando o contador de reparos.
    """
    inv = session.query(PlayerInventario).filter_by(id=inventario_id, player_id=player.id).first()
    if not inv:
        return False, "Item não encontrado no seu inventário.", 0

    if not getattr(inv, "danificado", False):
        return False, "Este item não precisa de reparos.", 0

    custo = calcular_custo_reparo(player, inv, proficiencia_nivel=proficiencia_nivel)
    if (player.ouro or 0) < custo:
        return False, f"Ouro insuficiente para o reparo. Custo: {custo} 💰 (Você tem: {player.ouro or 0} 💰).", 0

    player.ouro = (player.ouro or 0) - custo
    inv.danificado = False
    if inv.nome_item and "(Danificado)" in inv.nome_item:
        inv.nome_item = inv.nome_item.replace(" (Danificado)", "").replace("(Danificado)", "").strip()

    player.reparos_feitos_qtd = (player.reparos_feitos_qtd or 0) + 1

    try:
        from game.titulos import verificar_titulos_contadores
        verificar_titulos_contadores(session, player)
    except Exception:
        pass

    session.commit()
    return True, f"{inv.nome_item} reparado com sucesso por {custo} 💰!", custo


def vender_item(session, player, inventario_id):
    inv = session.query(PlayerInventario).filter_by(id=inventario_id, player_id=player.id).first()
    if not inv:
        raise ErroEconomia("Você não tem esse item.")
    if inv.equipado:
        raise ErroEconomia("Você não pode vender um item que está equipado. Desequipe-o antes de vender.")
    if inv.tipo_item not in ("arma", "armadura", "acessorio", "arma_armadura_forjada"):
        raise ErroEconomia("Esse tipo de item não pode ser vendido aqui.")

    preco = 0
    if inv.tipo_item == "arma":
        item_ref = session.query(Arma).filter_by(id=inv.item_ref_id).first()
        if item_ref:
            preco = item_ref.preco_venda_mercador if item_ref.preco_venda_mercador else int(round(item_ref.preco_compra * 0.4))
    elif inv.tipo_item == "armadura":
        item_ref = session.query(Armadura).filter_by(id=inv.item_ref_id).first()
        if item_ref:
            preco = item_ref.preco_venda_mercador if item_ref.preco_venda_mercador else int(round(item_ref.preco_compra * 0.4))
    elif inv.tipo_item == "acessorio":
        receita = session.query(Receita).filter_by(id=inv.item_ref_id).first()
        if receita:
            preco = int(round((receita.custo_base_ouro or 25) * 0.4))
        else:
            preco = 10
    else:
        preco = 10

    player.ouro = (player.ouro or 0) + preco
    if inv.quantidade > 1:
        inv.quantidade -= 1
    else:
        session.delete(inv)
    session.commit()
    return preco


def vender_tudo(session, player) -> tuple[int, int]:
    """
    Vende todos os equipamentos desequipados de uma só vez (regra de 40% vitrine).
    Retorna (total_ouro_ganho, total_itens_vendidos).
    """
    desequipados = (
        session.query(PlayerInventario)
        .filter(
            PlayerInventario.player_id == player.id,
            PlayerInventario.tipo_item.in_(["arma", "armadura", "acessorio", "arma_armadura_forjada"]),
            PlayerInventario.equipado == False,  # noqa: E712
        )
        .all()
    )
    if not desequipados:
        return 0, 0

    total_ouro = 0
    total_itens = 0

    for inv in desequipados:
        preco = 0
        if inv.tipo_item == "arma":
            item_ref = session.query(Arma).filter_by(id=inv.item_ref_id).first()
            if item_ref:
                preco = item_ref.preco_venda_mercador if item_ref.preco_venda_mercador else int(round(item_ref.preco_compra * 0.4))
        elif inv.tipo_item == "armadura":
            item_ref = session.query(Armadura).filter_by(id=inv.item_ref_id).first()
            if item_ref:
                preco = item_ref.preco_venda_mercador if item_ref.preco_venda_mercador else int(round(item_ref.preco_compra * 0.4))
        elif inv.tipo_item == "acessorio":
            receita = session.query(Receita).filter_by(id=inv.item_ref_id).first()
            if receita:
                preco = int(round((receita.custo_base_ouro or 25) * 0.4))
            else:
                preco = 10
        else:
            preco = 10

        qtd = inv.quantidade or 1
        total_ouro += preco * qtd
        total_itens += qtd
        session.delete(inv)

    player.ouro = (player.ouro or 0) + total_ouro
    session.commit()
    return total_ouro, total_itens


def calcular_preco_diagrama(receita: Receita) -> int:
    """Preço oficial do diagrama baseado no Tier da receita."""
    tier = (receita.tier or "").lower()
    if "sucata" in tier:
        return 50
    elif "bronze" in tier:
        return 150
    elif "ferro" in tier:
        return 350
    elif "aço" in tier or "aco" in tier:
        return 750
    return max(50, (receita.custo_base_ouro or 10) * 10)


def receita_desbloqueada(session, player, receita: Receita) -> bool:
    """
    Tier 1 básico (armas/armaduras comuns de Sucata) é liberado de início.
    Acessórios e Tiers 2+ exigem compra de diagrama via PlayerReceita.
    """
    if receita.tier == "Sucata Enferrujada" and receita.categoria != "Acessório":
        return True

    pr = session.query(PlayerReceita).filter_by(player_id=player.id, receita_id=receita.id).first()
    return bool(pr and pr.desbloqueada)


def comprar_diagrama(session, player, receita_id: int) -> tuple[Receita, int]:
    """Desbloqueia uma receita para forja debitando o custo em ouro do jogador."""
    receita = session.query(Receita).filter_by(id=receita_id).first()
    if not receita:
        raise ErroEconomia("Receita não encontrada.")

    if receita_desbloqueada(session, player, receita):
        raise ErroEconomia("Você já possui o diagrama desta receita.")

    preco = calcular_preco_diagrama(receita)
    if (player.ouro or 0) < preco:
        raise ErroEconomia(f"Ouro insuficiente. O diagrama custa {preco} 💰 e você possui {player.ouro or 0} 💰.")

    player.ouro = (player.ouro or 0) - preco
    pr = session.query(PlayerReceita).filter_by(player_id=player.id, receita_id=receita.id).first()
    if not pr:
        pr = PlayerReceita(player_id=player.id, receita_id=receita.id, desbloqueada=True)
        session.add(pr)
    else:
        pr.desbloqueada = True

    session.commit()
    return receita, preco


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

    if not receita_desbloqueada(session, player, receita):
        return False, "Diagrama bloqueado", []

    necessarios = obter_materiais_receita(receita)

    faltando = []
    for nome, qtd in necessarios:
        inv, tem = _tem_material(session, player, nome, qtd)
        if not tem:
            faltando.append(f"{nome} ({qtd}x)")

    custo = receita.custo_base_ouro or 0
    if player.ouro < custo:
        faltando.append(f"{custo} Ouro (você tem {player.ouro})")

    if faltando:
        return False, "Faltando: " + ", ".join(faltando), necessarios
    return True, "", necessarios


def forjar_item(session, player, receita_id):
    receita = session.query(Receita).filter_by(id=receita_id).first()
    if not receita:
        raise ErroEconomia("Receita não encontrada.")

    if not receita_desbloqueada(session, player, receita):
        raise ErroEconomia("Diagrama bloqueado! Compre o diagrama desta receita antes de forjá-la.")

    max_vagas = player.slots_mochila_max or 20
    if slots_mochila_ocupados(session, player) >= max_vagas:
        raise ErroEconomia(f"Mochila cheia! Limite de {max_vagas} vagas atingido. Libere espaço antes de forjar.")

    pode, motivo, necessarios = verificar_forja(session, player, receita_id)
    if not pode:
        raise ErroEconomia(motivo)

    for nome, qtd in necessarios:
        inv, _ = _tem_material(session, player, nome, qtd)
        if inv.quantidade > qtd:
            inv.quantidade -= qtd
        else:
            session.delete(inv)

    player.ouro -= (receita.custo_base_ouro or 0)

    nome_item = receita.tipo_slot
    item_ref_final = receita.id

    if receita.categoria == "Acessório":
        tipo_final = "acessorio"
    elif receita.categoria == "Ferramenta de Coleta":
        tipo_final = "ferramenta"
    elif receita.categoria == "Comida/Bebida":
        tipo_final = "consumivel"
    else:
        eh_armadura = receita.tipo_slot in (
            "Peitoral", "Escudo", "Elmo", "Luvas", "Bota", "Calça", "Calca", "Manopla"
        )
        item_real = None
        if eh_armadura:
            candidatos = session.query(Armadura).filter_by(tier=receita.tier).order_by(Armadura.id).all()
            item_real = next((a for a in candidatos if _normalizar(a.slot) == _normalizar(receita.tipo_slot)), None)
        else:
            candidatos = session.query(Arma).filter_by(tier=receita.tier).order_by(Arma.id).all()
            item_real = next((a for a in candidatos if _normalizar(a.tipo) == _normalizar(receita.tipo_slot)), None)
        if item_real:
            nome_item = item_real.variacao
            item_ref_final = item_real.id
            tipo_final = "armadura" if eh_armadura else "arma"
        else:
            tipo_final = "arma_armadura_forjada"

    novo = PlayerInventario(
        player_id=player.id,
        tipo_item=tipo_final,
        item_ref_id=item_ref_final, nome_item=nome_item, quantidade=1, equipado=False,
    )
    session.add(novo)
    session.commit()
    return novo
