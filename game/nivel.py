"""
Level Up — NUNCA EXISTIA em lugar nenhum do código antes disso. XP se
acumulava infinito em player.xp_atual sem nunca virar Nível. Isso corrige
isso: verifica o threshold da Curva Mestra, sobe (pode subir vários níveis
de uma vez se o XP ganho for suficiente), atualiza HP/Mana máximos, e
restaura HP/Mana como recompensa de subir.
"""

NIVEL_MAXIMO_PERSONAGEM = 75
NIVEL_MAXIMO = NIVEL_MAXIMO_PERSONAGEM  # Alias para compatibilidade retroativa


def verificar_e_aplicar_level_up(session, player):
    """Retorna lista de niveis alcancados nesta chamada (vazia se nao subiu)."""
    from db.models import CurvaMestra

    niveis_subidos = []
    while player.nivel < NIVEL_MAXIMO_PERSONAGEM:
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
            from game.atributos import calcular_hp_maximo, calcular_vigor_maximo
            player.hp_max = calcular_hp_maximo(player, session)
            player.hp_atual = player.hp_max  # recompensa de subir: cura total
            player.vig_max = calcular_vigor_maximo(player)
            player.vig_atual = player.vig_max
            if curva_novo.mana is not None:
                from game.atributos import calcular_mana_maximo
                player.mana_max = calcular_mana_maximo(player=player, session=session, nivel=player.nivel)
                player.mana_atual = player.mana_max

    if niveis_subidos:
        from game.talentos import conceder_talentos_classe
        conceder_talentos_classe(session, player)
        session.commit()
    return niveis_subidos





def calcular_upgrade_rank(session, player):
    """
    Retorna dict com o que o jogador PODE fazer agora em relação ao rank da
    habilidade ativa, sem alterar nada no banco (só leitura).
    """
    from db.models import HabilidadeAtiva

    NIVEL_MINIMO_POR_RANK = {2: 10, 3: 25, 4: 50, 5: 73}

    rank_atual = player.habilidade_ativa_nivel or 1
    if rank_atual >= 5:
        return {"pode_upar": False, "motivo": "rank_maximo", "proximo_rank": None,
                "custo": None, "nivel_necessario": None}

    proximo_rank = rank_atual + 1
    nivel_necessario = NIVEL_MINIMO_POR_RANK[proximo_rank]

    hab = None
    if player.classe_id:
        hab = session.query(HabilidadeAtiva).filter_by(classe_id=player.classe_id).first()
    if not hab:
        return {"pode_upar": False, "motivo": "habilidade_nao_encontrada",
                "proximo_rank": proximo_rank, "custo": None,
                "nivel_necessario": nivel_necessario}

    custo = getattr(hab, f"custo_upgrade_ouro_rank{proximo_rank}")

    if player.nivel < nivel_necessario:
        return {"pode_upar": False, "motivo": "nivel_insuficiente",
                "proximo_rank": proximo_rank, "custo": custo,
                "nivel_necessario": nivel_necessario}

    if (player.ouro or 0) < (custo or 0):
        return {"pode_upar": False, "motivo": "ouro_insuficiente",
                "proximo_rank": proximo_rank, "custo": custo,
                "nivel_necessario": nivel_necessario}

    return {"pode_upar": True, "motivo": None, "proximo_rank": proximo_rank,
            "custo": custo, "nivel_necessario": nivel_necessario, "habilidade": hab}


def aplicar_upgrade_rank(session, player):
    """Executa o upgrade. Assume que calcular_upgrade_rank já confirmou pode_upar=True.
    Levanta ValueError se as condições não baterem mais (dupla checagem antes de gastar)."""
    resultado = calcular_upgrade_rank(session, player)
    if not resultado["pode_upar"]:
        raise ValueError(resultado["motivo"])
    player.ouro -= resultado["custo"]
    player.habilidade_ativa_nivel = resultado["proximo_rank"]
    return resultado
