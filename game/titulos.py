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


def listar_todos_titulos(session):
    from db.models import Titulo
    return session.query(Titulo).order_by(Titulo.id).all()


def equipar_titulo(session, player, titulo_id_ou_none):
    """Equipa ou desequipa um título para o jogador."""
    from db.models import Titulo, PlayerTitulo

    if titulo_id_ou_none is None or titulo_id_ou_none == 0:
        player.titulo_ativo = None
        session.commit()
        return None

    pt = (
        session.query(PlayerTitulo)
        .filter_by(player_id=player.id, titulo_id=titulo_id_ou_none)
        .first()
    )
    if not pt:
        raise ValueError("Título não desbloqueado.")

    t = session.query(Titulo).filter_by(id=titulo_id_ou_none).first()
    player.titulo_ativo = t.nome
    session.commit()
    return t



def verificar_titulos_contadores(session, player) -> list:
    """
    Verifica os contadores do Player para conceder os 6 novos títulos (Item 8):
    - Veterano de Mil Batalhas: vencer_combates_qtd >= 100
    - Açougueiro: vencer_combates_qtd >= 250
    - Sobrevivente Nato: fugas_com_sucesso_qtd >= 25
    - Ferreiro de Mão Cheia: reparos_feitos_qtd >= 20
    - Bolso Fundo: ouro_acumulado_pico >= 5000 (ou player.ouro >= 5000)
    - Mestre de Uma Só Arma: proficiência em qualquer arma >= 20
    Retorna lista de títulos concedidos nesta checagem.
    """
    from db.models import Titulo, PlayerTitulo, PlayerProficiencia
    from game.proficiencia import nivel_e_progresso

    # Atualiza pico de ouro se ouro atual for maior
    if player.ouro and (player.ouro_acumulado_pico or 0) < player.ouro:
        player.ouro_acumulado_pico = player.ouro

    candidatos = session.query(Titulo).filter_by(condicao_tipo="contador_generico").all()
    ja_tem_ids = {
        pt.titulo_id
        for pt in session.query(PlayerTitulo).filter_by(player_id=player.id).all()
    }

    concedidos = []
    vitorias = player.combates_vencidos_qtd or 0
    fugas = player.fugas_com_sucesso_qtd or 0
    reparos = player.reparos_feitos_qtd or 0
    pico_ouro = max(player.ouro_acumulado_pico or 0, player.ouro or 0)

    max_nv_prof = 0
    profs = session.query(PlayerProficiencia).filter_by(player_id=player.id).all()
    for pr in profs:
        nv, _, _ = nivel_e_progresso(pr.valor)
        if nv > max_nv_prof:
            max_nv_prof = nv

    for t in candidatos:
        if t.id in ja_tem_ids:
            continue
        c_val = t.condicao_valor or ""
        atingiu = False
        if "vencer_combates_qtd=100" in c_val:
            atingiu = (vitorias >= 100)
        elif "vencer_combates_qtd=250" in c_val:
            atingiu = (vitorias >= 250)
        elif "fugas_com_sucesso_qtd=25" in c_val:
            atingiu = (fugas >= 25)
        elif "reparos_feitos_qtd=20" in c_val:
            atingiu = (reparos >= 20)
        elif "ouro_acumulado_pico=5000" in c_val:
            atingiu = (pico_ouro >= 5000)
        elif "proficiencia_nivel_max_qtd=20" in c_val:
            atingiu = (max_nv_prof >= 20)

        if atingiu:
            session.add(PlayerTitulo(player_id=player.id, titulo_id=t.id))
            concedidos.append(t)

    if concedidos:
        session.commit()
    return concedidos

