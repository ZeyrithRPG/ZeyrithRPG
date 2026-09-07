"""
Codex — Knowledge progressivo por monstro (0-5), revela informação aos poucos.
Nv0: nunca visto -> "???"
Nv1: encontrado em combate -> nome, papel, nivel
Nv2: venceu 1x -> HP/Dano/Defesa, golpe especial
Nv3: venceu 2x -> efeito mecanico, materiais dropados
Nv4: venceu 3x -> fraqueza (o campo ja dizia "Knowledge 4-5" na planilha)
Nv5: venceu 5x -> motivacao/lore, loot unico
"""

NIVEL_MAX = 5


def _registro(session, player, monstro_id):
    from db.models import PlayerKnowledge
    reg = (
        session.query(PlayerKnowledge)
        .filter_by(player_id=player.id, monstro_id=monstro_id)
        .first()
    )
    if not reg:
        reg = PlayerKnowledge(player_id=player.id, monstro_id=monstro_id, nivel_knowledge=0)
        session.add(reg)
    return reg


def registrar_encontro(session, player, monstro_id):
    """Chamado quando o combate comeca -- garante nivel minimo 1."""
    reg = _registro(session, player, monstro_id)
    if reg.nivel_knowledge < 1:
        reg.nivel_knowledge = 1
    session.commit()
    return reg.nivel_knowledge


def registrar_vitoria(session, player, monstro_id):
    """Chamado quando o jogador vence -- sobe 1 nivel, ate o maximo."""
    reg = _registro(session, player, monstro_id)
    reg.nivel_knowledge = min(NIVEL_MAX, reg.nivel_knowledge + 1)
    session.commit()
    return reg.nivel_knowledge


def nivel_do_jogador(session, player, monstro_id):
    from db.models import PlayerKnowledge
    reg = (
        session.query(PlayerKnowledge)
        .filter_by(player_id=player.id, monstro_id=monstro_id)
        .first()
    )
    return reg.nivel_knowledge if reg else 0


def info_revelada(monstro, nivel):
    """Retorna um dict com so os campos que esse nivel de Knowledge ja libera."""
    info = {}
    if nivel >= 1:
        info["nome"] = monstro.nome
        info["papel"] = monstro.papel
        info["nivel_monstro"] = monstro.nivel
    if nivel >= 2:
        info["hp"] = monstro.hp
        info["dano"] = monstro.dano
        info["defesa"] = monstro.defesa
        info["golpe_especial"] = monstro.golpe_especial
    if nivel >= 3:
        info["efeito_mecanico"] = monstro.efeito_mecanico
        info["materiais_dropados"] = monstro.materiais_dropados
    if nivel >= 4:
        info["fraqueza"] = monstro.fraqueza
    if nivel >= 5:
        info["motivacao"] = monstro.motivacao
        info["loot_unico"] = monstro.loot_unico
    return info
