"""
Fase 5 — Missões e Mural da Milícia (Reset Diário e Rastreamento Incremental).
Regras oficiais baseadas na planilha balanceamento_rpg-13.xlsx.
"""
import re
import random
from datetime import date
from db.models import Missao, PlayerQuest, PlayerReputacaoFaccao, Tier

TIER_PARA_FACCAO = {
    "Sucata Enferrujada": "A Milícia dos Desamparados", "Bronze": "A Milícia dos Desamparados",
    "Ferro": "A Guilda dos Picaretas Negros", "Prata": "A Guilda dos Picaretas Negros",
    "Aço Élfico": "A Vigília das Folhas de Prata", "Mecanismo Anão": "Clã Martelo de Vapor",
    "Vidro Vulcânico": "O Conselho dos Mestres de Forja", "Ferro Órquico": "O Conselho dos Mestres de Forja",
    "Mithril": "Os Navegadores do Abismo", "Ébano": "Os Navegadores do Abismo",
    "Adamantina": "A Ordem dos Cavaleiros do Dragão Decaído", "Osso de Dragão": "A Ordem dos Cavaleiros do Dragão Decaído",
    "Pacto Daédrico": "Os Guardiões do Último Véu", "Estelar / Cósmico": "Os Guardiões do Último Véu",
}

HONRA_POR_CATEGORIA_HONRA = {"comum": 10, "veterano": 15, "lendario": 25, "lendário": 25}


class ErroMissao(Exception):
    pass


def _honra_minima(texto_requisito):
    if not texto_requisito:
        return 0
    m = re.search(r"(\d+)", texto_requisito)
    return int(m.group(1)) if m else 0


def honra_do_player(session, player, faccao):
    rep = (
        session.query(PlayerReputacaoFaccao)
        .filter_by(player_id=player.id, faccao=faccao)
        .first()
    )
    return rep.pontos if rep else 0


def ganhar_honra(session, player, faccao, pontos):
    rep = (
        session.query(PlayerReputacaoFaccao)
        .filter_by(player_id=player.id, faccao=faccao)
        .first()
    )
    if not rep:
        rep = PlayerReputacaoFaccao(player_id=player.id, faccao=faccao, pontos=0)
        session.add(rep)
    rep.pontos = max(-100, min(100, rep.pontos + pontos))
    return rep.pontos


def barra_compacta(atual: int, meta: int, blocos: int = 3) -> str:
    """Gera barras compactas como 🟩🟩⬛ de acordo com a proporção."""
    if meta <= 0:
        return "🟩" * blocos
    proporcao = min(1.0, max(0.0, atual / meta))
    cheios = round(proporcao * blocos)
    if atual > 0 and cheios == 0:
        cheios = 1
    return ("🟩" * cheios) + ("⬛" * (blocos - cheios))


def extrair_dados_objetivo(missao: Missao) -> tuple[str, int, str]:
    """
    Analisa a descrição/categoria da missão e extrai:
    (tipo_objetivo: 'abate' | 'coleta', meta: int, alvo: str)
    """
    texto = (missao.objetivo or "") + " " + (missao.nome or "")
    cat = (missao.categoria or "").lower()

    # Meta numérica
    m_num = re.search(r"\b(\d+)x?\b", missao.objetivo or "")
    meta = int(m_num.group(1)) if m_num else (1 if "elite" in cat or "boss" in cat else 3)
    if meta <= 0 or meta > 20:
        meta = 3

    if "coleta" in cat or "traga" in texto.lower() or "colete" in texto.lower() or "trazer" in texto.lower():
        tipo = "coleta"
        # Tenta achar o nome do material (ex: "Trazer 4x Minério de Bronze Sulfuroso")
        m_alvo = re.search(r"(?:traga|trazer|colete|coletar)\s+(?:\d+x?\s+)?([^,.;]+)", texto, re.IGNORECASE)
        alvo = m_alvo.group(1).strip() if m_alvo else "Recurso"
        # Limpa palavras extras
        alvo = re.sub(r"^(pro|pra|para|o|a|os|as|de|do|da)\s+", "", alvo, flags=re.IGNORECASE).strip()
    else:
        tipo = "abate"
        m_alvo = re.search(r"(?:mate|matar|derrote|derrotar|elimine|eliminar|enfrente|confronte)\s+(?:o|a|os|as)?\s*([^,.;]+)", texto, re.IGNORECASE)
        alvo = m_alvo.group(1).strip() if m_alvo else "Monstros"
        alvo = re.sub(r"^(que|pro|pra|para|o|a|os|as|de|do|da)\s+", "", alvo, flags=re.IGNORECASE).strip()

    return tipo, meta, alvo[:60]


def tiers_do_polo_atual(session, player) -> list[str]:
    """Descobre os tiers cobertos pelo polo atual do jogador."""
    from game.mapa import cidade_polo_do_local
    cidade = cidade_polo_do_local(session, player.local_atual or "Vila Inicial")
    if cidade and cidade.tiers_cobertos:
        # Ex: "Sucata Enferrujada + Bronze" -> ["Sucata Enferrujada", "Bronze"]
        partes = [t.strip() for t in cidade.tiers_cobertos.split("+")]
        return partes
    # Fallback para o tier do jogador
    tiers = session.query(Tier).order_by(Tier.id).all()
    idx = max(0, min((player.tier_mais_alto_alcancado or 1) - 1, len(tiers) - 1))
    return [tiers[idx].nome] if tiers else ["Sucata Enferrujada"]


def gerar_contratos_diarios(session, player, quantidade: int = 3):
    """Gera até 3 contratos diários do polo atual para o Mural da Milícia."""
    tiers = tiers_do_polo_atual(session, player)
    todas_missoes = (
        session.query(Missao)
        .filter(Missao.tier.in_(tiers), Missao.is_principal == False)  # noqa: E712
        .all()
    )
    if not todas_missoes:
        todas_missoes = session.query(Missao).filter_by(is_principal=False).limit(20).all()

    # IDs de contratos diários ativos no momento
    ativos = session.query(PlayerQuest).filter_by(player_id=player.id, status="em_andamento").all()
    ids_em_andamento = {pq.quest_id for pq in ativos}

    candidatas = [m for m in todas_missoes if m.id not in ids_em_andamento]
    random.shuffle(candidatas)

    escolhidas = candidatas[:max(0, quantidade - len(ativos))]
    for m in escolhidas:
        tipo, meta, alvo = extrair_dados_objetivo(m)
        pq = PlayerQuest(
            player_id=player.id,
            quest_id=m.id,
            status="em_andamento",
            progresso_atual=0,
            progresso_meta=meta,
            tipo_objetivo=tipo,
            alvo_id_ou_nome=alvo,
            local_alvo=player.local_atual or "Vila Inicial",
        )
        session.add(pq)


def checar_e_executar_reset_diario(session, player) -> bool:
    """
    Gatilho de 00:00 (baseado em data ISO YYYY-MM-DD):
    - Reinicializa os 2 rerolls diários.
    - Garante a presença dos 3 contratos diários do polo atual no Mural.
    - Idempotente e persistente no banco de dados.
    """
    hoje = date.today().isoformat()
    if player.ultimo_reset_missoes == hoje:
        return False

    player.rerolls_restantes = 2
    player.ultimo_reset_missoes = hoje

    gerar_contratos_diarios(session, player, quantidade=3)
    session.commit()
    return True


def reroll_missao(session, player, quest_id: int):
    """Substitui um contrato ativo consumindo 1 reroll diário."""
    checar_e_executar_reset_diario(session, player)

    if (player.rerolls_restantes or 0) <= 0:
        raise ErroMissao("Você já usou seus 2 rerolls diários hoje.")

    pq = (
        session.query(PlayerQuest)
        .filter(
            PlayerQuest.player_id == player.id,
            (PlayerQuest.quest_id == quest_id) | (PlayerQuest.id == quest_id),
            PlayerQuest.status.in_(["em_andamento", "disponivel"]),
        )
        .first()
    )
    if not pq:
        raise ErroMissao("Contrato não encontrado ou já concluído.")

    tiers = tiers_do_polo_atual(session, player)
    ativos_ids = {p.quest_id for p in session.query(PlayerQuest).filter_by(player_id=player.id, status="em_andamento").all()}

    candidatas = (
        session.query(Missao)
        .filter(Missao.tier.in_(tiers), Missao.is_principal == False, ~Missao.id.in_(ativos_ids))  # noqa: E712
        .all()
    )
    if not candidatas:
        candidatas = session.query(Missao).filter(Missao.is_principal == False, ~Missao.id.in_(ativos_ids)).all()  # noqa: E712

    if not candidatas:
        raise ErroMissao("Não há outros contratos disponíveis neste polo para trocar.")

    nova_missao = random.choice(candidatas)
    tipo, meta, alvo = extrair_dados_objetivo(nova_missao)

    player.rerolls_restantes = max(0, player.rerolls_restantes - 1)
    pq.quest_id = nova_missao.id
    pq.progresso_atual = 0
    pq.progresso_meta = meta
    pq.tipo_objetivo = tipo
    pq.alvo_id_ou_nome = alvo
    pq.local_alvo = player.local_atual or "Vila Inicial"
    session.commit()
    return nova_missao


def registrar_abate(session, player, monstro_nome: str, monstro_id: int = None, local: str = None) -> list[str]:
    """Incrementa o progresso de contratos ativos de abate compatíveis com o monstro morto."""
    checar_e_executar_reset_diario(session, player)
    mensagens = []
    quests_abate = (
        session.query(PlayerQuest)
        .filter_by(player_id=player.id, status="em_andamento", tipo_objetivo="abate")
        .all()
    )
    nome_low = (monstro_nome or "").lower()

    for pq in quests_abate:
        missao = session.get(Missao, pq.quest_id)
        if not missao:
            continue
        alvo_low = (pq.alvo_id_ou_nome or "").lower()
        obj_low = (missao.objetivo or "").lower()

        # Compatibilidade: se cita o monstro ou é genérico para o tier/polo
        eh_compativel = (
            alvo_low in nome_low
            or nome_low in alvo_low
            or any(parte in nome_low for parte in alvo_low.split() if len(parte) >= 4)
            or "monstro" in alvo_low
            or "qualquer" in alvo_low
            or nome_low in obj_low
        )

        if eh_compativel and (pq.progresso_atual or 0) < (pq.progresso_meta or 1):
            pq.progresso_atual = (pq.progresso_atual or 0) + 1
            barra = barra_compacta(pq.progresso_atual, pq.progresso_meta)
            if pq.progresso_atual >= pq.progresso_meta:
                mensagens.append(f"📜 *{missao.nome}*: {barra} {pq.progresso_atual}/{pq.progresso_meta} (COMPLETO! ✅)")
            else:
                mensagens.append(f"📜 *{missao.nome}*: {barra} {pq.progresso_atual}/{pq.progresso_meta}")

    if mensagens:
        session.commit()
    return mensagens


def registrar_coleta(session, player, material_nome: str, quantidade: int = 1, local: str = None) -> list[str]:
    """Incrementa o progresso de contratos ativos de coleta compatíveis com o material recolhido."""
    checar_e_executar_reset_diario(session, player)
    mensagens = []
    quests_coleta = (
        session.query(PlayerQuest)
        .filter_by(player_id=player.id, status="em_andamento", tipo_objetivo="coleta")
        .all()
    )
    mat_low = (material_nome or "").lower()

    for pq in quests_coleta:
        missao = session.get(Missao, pq.quest_id)
        if not missao:
            continue
        alvo_low = (pq.alvo_id_ou_nome or "").lower()
        obj_low = (missao.objetivo or "").lower()

        eh_compativel = (
            alvo_low in mat_low
            or mat_low in alvo_low
            or any(parte in mat_low for parte in alvo_low.split() if len(parte) >= 4)
            or mat_low in obj_low
        )

        if eh_compativel and (pq.progresso_atual or 0) < (pq.progresso_meta or 1):
            pq.progresso_atual = min(pq.progresso_meta, (pq.progresso_atual or 0) + quantidade)
            barra = barra_compacta(pq.progresso_atual, pq.progresso_meta)
            if pq.progresso_atual >= pq.progresso_meta:
                mensagens.append(f"🧺 *{missao.nome}*: {barra} {pq.progresso_atual}/{pq.progresso_meta} (COMPLETO! ✅)")
            else:
                mensagens.append(f"🧺 *{missao.nome}*: {barra} {pq.progresso_atual}/{pq.progresso_meta}")

    if mensagens:
        session.commit()
    return mensagens


def listar_missoes_disponiveis(session, player, tier_nome):
    """Lista missões disponíveis com base na Honra da facção do tier."""
    checar_e_executar_reset_diario(session, player)

    faccao = TIER_PARA_FACCAO.get(tier_nome)
    honra_atual = honra_do_player(session, player, faccao) if faccao else 0

    todas = session.query(Missao).filter_by(tier=tier_nome).all()
    ja_aceitas_ids = {
        pq.quest_id for pq in session.query(PlayerQuest).filter_by(player_id=player.id).all()
    }

    disponiveis = []
    for m in todas:
        if m.id in ja_aceitas_ids:
            continue
        if _honra_minima(m.requisito_honra) > honra_atual:
            continue
        disponiveis.append(m)
    return disponiveis


def aceitar_missao(session, player, missao_id):
    checar_e_executar_reset_diario(session, player)

    missao = session.query(Missao).filter_by(id=missao_id).first()
    if not missao:
        raise ErroMissao("Missão não encontrada.")

    existente = session.query(PlayerQuest).filter_by(player_id=player.id, quest_id=missao_id).first()
    if existente:
        raise ErroMissao("Você já aceitou essa missão.")

    tipo, meta, alvo = extrair_dados_objetivo(missao)
    pq = PlayerQuest(
        player_id=player.id,
        quest_id=missao_id,
        status="em_andamento",
        progresso_atual=0,
        progresso_meta=meta,
        tipo_objetivo=tipo,
        alvo_id_ou_nome=alvo,
        local_alvo=player.local_atual or "Vila Inicial",
    )
    session.add(pq)
    session.commit()
    return pq


def completar_missao(session, player, missao_id):
    """
    Entrega de missão com validação estrita de progresso.
    Trava contra entrega cega: lança ErroMissao se o objetivo não estiver 100% completo.
    """
    checar_e_executar_reset_diario(session, player)

    pq = (
        session.query(PlayerQuest)
        .filter(
            PlayerQuest.player_id == player.id,
            (PlayerQuest.quest_id == missao_id) | (PlayerQuest.id == missao_id),
            PlayerQuest.status == "em_andamento",
        )
        .first()
    )
    if not pq:
        raise ErroMissao("Essa missão não está em andamento para você.")

    # TRAVA CONTRA ENTREGA CEGA
    if (pq.progresso_atual or 0) < (pq.progresso_meta or 1):
        raise ErroMissao(f"Objetivo incompleto! Progresso atual: {pq.progresso_atual}/{pq.progresso_meta}.")

    missao = session.query(Missao).filter_by(id=pq.quest_id).first()

    ouro = 0
    if isinstance(missao.recompensa, (int, float)):
        ouro = int(missao.recompensa)
    elif isinstance(missao.recompensa, str):
        m = re.search(r"\d+", missao.recompensa)
        ouro = int(m.group()) if m else 0
    player.ouro = (player.ouro or 0) + ouro

    if missao.is_principal and missao.recompensa_xp:
        player.xp_atual = (player.xp_atual or 0) + missao.recompensa_xp

    from game.nivel import verificar_e_aplicar_level_up
    niveis_subidos = verificar_e_aplicar_level_up(session, player)

    faccao = TIER_PARA_FACCAO.get(missao.tier)
    honra_ganha = 0
    if faccao:
        chave_honra = (missao.requisito_honra or "comum").split(" ")[0].lower()
        honra_ganha = HONRA_POR_CATEGORIA_HONRA.get(chave_honra, 10)
        ganhar_honra(session, player, faccao, honra_ganha)

    pq.status = "concluida"
    session.commit()
    return ouro, honra_ganha, faccao, missao.recompensa_extra, niveis_subidos


verificar_e_aplicar_reset_diario = checar_e_executar_reset_diario

