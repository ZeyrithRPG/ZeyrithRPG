"""
Narrativa — abertura + narração de transição de Ato, disparada pelo Nível
real do jogador (não pelo tier_mais_alto_alcancado, que ainda não é
atualizado em lugar nenhum do código).
"""

TIERS_POR_ATO = {
    1: ["Sucata Enferrujada", "Bronze", "Ferro"],
    2: ["Prata", "Aco Elfico", "Mecanismo Anao"],
    3: ["Vidro Vulcanico", "Ferro Orquico", "Mithril"],
    4: ["Ebano", "Adamantina", "Osso de Dragao"],
    5: ["Pacto Daedrico", "Estelar / Cosmico"],
}


def ato_do_nivel(session, nivel):
    from db.models import Tier

    tiers = {t.nome: t for t in session.query(Tier).all()}
    ato_atual = 0
    for ato, nomes_tier in TIERS_POR_ATO.items():
        primeiro_tier = tiers.get(nomes_tier[0])
        if primeiro_tier and primeiro_tier.nivel_min and nivel >= primeiro_tier.nivel_min:
            ato_atual = ato
    return ato_atual


def checar_narracao_pendente(session, player):
    """Se o jogador acabou de entrar num Ato novo, retorna a Narrativa
    (e já marca como mostrada). Senão, retorna None."""
    from db.models import Narrativa

    ato_real = ato_do_nivel(session, player.nivel or 1)
    if ato_real <= (player.maior_ato_narrado or 0):
        return None

    numeral = ["I", "II", "III", "IV", "V"][ato_real - 1]
    narrativa = (
        session.query(Narrativa)
        .filter(Narrativa.tipo == "Transição de Ato", Narrativa.titulo.like(f"Ato {numeral} —%"))
        .first()
    )
    player.maior_ato_narrado = ato_real
    return narrativa


def sincronizar_tier(session, player):
    """tier_mais_alto_alcancado nunca era atualizado em lugar nenhum do codigo --
    isso corrige isso, chamando toda vez que o HUD e mostrado. So sobe, nunca desce
    (mesmo se o Nivel cair por algum motivo, o Tier ja alcancado fica alcancado)."""
    from db.models import Tier

    tiers = session.query(Tier).order_by(Tier.id).all()
    nivel = player.nivel or 1
    idx_real = 1
    for i, t in enumerate(tiers, start=1):
        if t.nivel_min and nivel >= t.nivel_min:
            idx_real = i
    if idx_real > (player.tier_mais_alto_alcancado or 1):
        player.tier_mais_alto_alcancado = idx_real
        return True
    return False
