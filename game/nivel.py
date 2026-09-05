"""
Level Up — NUNCA EXISTIA em lugar nenhum do código antes disso. XP se
acumulava infinito em player.xp_atual sem nunca virar Nível. Isso corrige
isso: verifica o threshold da Curva Mestra, sobe (pode subir vários níveis
de uma vez se o XP ganho for suficiente), atualiza HP/Mana máximos, e
restaura HP/Mana como recompensa de subir.
"""

NIVEL_MAXIMO = 75


def verificar_e_aplicar_level_up(session, player):
    """Retorna lista de niveis alcancados nesta chamada (vazia se nao subiu)."""
    from db.models import CurvaMestra

    niveis_subidos = []
    while player.nivel < NIVEL_MAXIMO:
        curva_atual = session.query(CurvaMestra).filter_by(nivel=player.nivel).first()
        if not curva_atual or not curva_atual.xp_prox_nivel:
            break
        if player.xp_atual < curva_atual.xp_prox_nivel:
            break

        player.xp_atual -= curva_atual.xp_prox_nivel
        player.nivel += 1
        niveis_subidos.append(player.nivel)

        curva_novo = session.query(CurvaMestra).filter_by(nivel=player.nivel).first()
        if curva_novo:
            from game.atributos import bonus_hp_por_con
            bonus_con = bonus_hp_por_con(player.atributo_con or 10)
            player.hp_max = curva_novo.hp + bonus_con
            player.hp_atual = player.hp_max  # recompensa de subir: cura total
            if curva_novo.mana and player.mana_max:
                player.mana_max = curva_novo.mana
                player.mana_atual = player.mana_max

    if niveis_subidos:
        session.commit()
    return niveis_subidos
