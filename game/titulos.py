"""
Fase 5 — Títulos: verifica condição e concede.
Por ora, so cobre titulos ligados a poupar um monstro especifico (a maioria dos 17).
Titulos ligados a outras condicoes (Reputacao 100, etc) ficam pra quando o resto
do sistema existir.
"""


def verificar_titulo_por_poupar(session, player, nome_monstro_poupado):
    from db.models import Titulo, PlayerTitulo

    nome_curto = nome_monstro_poupado.split(",")[0].strip()

    candidatos = session.query(Titulo).all()
    concedidos = []
    for t in candidatos:
        if not t.condicao or nome_curto not in t.condicao:
            continue
        ja_tem = (
            session.query(PlayerTitulo)
            .filter_by(player_id=player.id, titulo_id=t.id)
            .first()
        )
        if ja_tem:
            continue
        session.add(PlayerTitulo(player_id=player.id, titulo_id=t.id))
        concedidos.append(t)
    if concedidos:
        session.commit()
    return concedidos


def listar_titulos_do_player(session, player):
    from db.models import PlayerTitulo, Titulo

    return (
        session.query(Titulo)
        .join(PlayerTitulo, PlayerTitulo.titulo_id == Titulo.id)
        .filter(PlayerTitulo.player_id == player.id)
        .all()
    )
