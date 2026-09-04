"""
Fase 5 — Missões: listar/aceitar/completar, ganho de Honra por facção.
"""
import re

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
    from db.models import PlayerReputacaoFaccao
    rep = (
        session.query(PlayerReputacaoFaccao)
        .filter_by(player_id=player.id, faccao=faccao)
        .first()
    )
    return rep.pontos if rep else 0


def ganhar_honra(session, player, faccao, pontos):
    from db.models import PlayerReputacaoFaccao
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


def listar_missoes_disponiveis(session, player, tier_nome):
    """So mostra missao cuja Honra requerida o jogador ja tem na faccao do tier."""
    from db.models import Missao, PlayerQuest

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
    from db.models import Missao, PlayerQuest

    missao = session.query(Missao).filter_by(id=missao_id).first()
    if not missao:
        raise ErroMissao("Missão não encontrada.")

    existente = session.query(PlayerQuest).filter_by(player_id=player.id, quest_id=missao_id).first()
    if existente:
        raise ErroMissao("Você já aceitou essa missão.")

    pq = PlayerQuest(player_id=player.id, quest_id=missao_id, status="em_andamento")
    session.add(pq)
    session.commit()
    return pq


def completar_missao(session, player, missao_id):
    """Marca concluida, da recompensa e Honra. Nao verifica objetivo automaticamente
    ainda (isso exigiria rastrear cada tipo de objetivo -- fica pra depois; por ora
    o jogador confirma manualmente que cumpriu, como um 'honor system' de mesa."""
    from db.models import Missao, PlayerQuest

    pq = session.query(PlayerQuest).filter_by(player_id=player.id, quest_id=missao_id).first()
    if not pq or pq.status != "em_andamento":
        raise ErroMissao("Essa missão não está em andamento pra você.")

    missao = session.query(Missao).filter_by(id=missao_id).first()

    ouro = 0
    if isinstance(missao.recompensa, (int, float)):
        ouro = int(missao.recompensa)
    elif isinstance(missao.recompensa, str):
        m = re.search(r"\d+", missao.recompensa)
        ouro = int(m.group()) if m else 0
    player.ouro += ouro

    if missao.is_principal and missao.recompensa_xp:
        player.xp_atual += missao.recompensa_xp

    faccao = TIER_PARA_FACCAO.get(missao.tier)
    honra_ganha = 0
    if faccao:
        chave_honra = (missao.requisito_honra or "comum").split(" ")[0].lower()
        honra_ganha = HONRA_POR_CATEGORIA_HONRA.get(chave_honra, 10)
        ganhar_honra(session, player, faccao, honra_ganha)

    pq.status = "concluida"
    session.commit()
    return ouro, honra_ganha, faccao, missao.recompensa_extra
