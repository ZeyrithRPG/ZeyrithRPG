"""
Fase 6 — Mapa: locais visiveis (respeitando Secreto), viajar, Covil de Boss.
"""
import re


def _monstros_do_gatilho_secreto(descricao_local):
    """'Só revelado se a Criança Marcada ou o Batedor Ferido em Fuga forem poupados.'
    -> ['Criança Marcada', 'Batedor Ferido em Fuga']"""
    if not descricao_local:
        return []
    m = re.search(r"se (.+?) (?:for|forem) poupad", descricao_local, re.IGNORECASE)
    if not m:
        return []
    nomes = [n.strip() for n in m.group(1).split(" ou ")]
    return [re.sub(r"^(a|o|à|ao)\s+", "", n, flags=re.IGNORECASE) for n in nomes]


def local_esta_desbloqueado(local, player):
    if local.tipo != "Local Secreto":
        return True
    gatilhos = _monstros_do_gatilho_secreto(local.descricao)
    poupados = (player.monstros_poupados or "").split("|")
    return any(g in poupados for g in gatilhos)


def listar_locais_visiveis(session, player, tier_nome_atual=None):
    from db.models import Local

    todos = session.query(Local).order_by(Local.id).all()
    visiveis = []
    for local in todos:
        if not local_esta_desbloqueado(local, player):
            continue
        # local muito acima do nivel do jogador fica visivel mas travado (nao escondido)
        local.travado = bool(local.nivel_ref and player.nivel and local.nivel_ref > (player.nivel + 15))
        visiveis.append(local)
    return visiveis


def monstro_do_covil(session, local):
    """Pega o(s) nome(s) exclusivo(s) do Covil de Boss a partir do campo o_que_tem,
    e retorna o Monstro real correspondente (o primeiro que achar no banco)."""
    from db.models import Monstro

    if local.tipo != "Covil de Boss" or not local.o_que_tem:
        return None

    nomes_candidatos = [n.strip() for n in local.o_que_tem.split(",")]
    for candidato in nomes_candidatos:
        nome_limpo = re.sub(r"\s*\(exclusivo\)\s*", "", candidato).strip()
        monstro = session.query(Monstro).filter(Monstro.nome.like(f"{nome_limpo}%")).first()
        if monstro:
            return monstro
    return None
