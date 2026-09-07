"""
Descanso — resolve o fato de nao existir NENHUMA forma de recuperar Vigor
no jogo hoje. So funciona em Cidade (nao em locais de perigo), custa Ouro
conforme a Cidade atual (dado que ja existia na planilha e nunca foi usado).
"""


class ErroDescanso(Exception):
    pass


def _cidade_do_local_atual(session, player):
    from db.models import Cidade, Local
    local = session.query(Local).filter_by(nome=player.local_atual).first()
    if not local or local.tipo != "Cidade":
        return None
    return session.query(Cidade).filter_by(nome=local.nome).first()


def pode_descansar(session, player):
    cidade = _cidade_do_local_atual(session, player)
    return cidade is not None


def descansar(session, player):
    cidade = _cidade_do_local_atual(session, player)
    if not cidade:
        raise ErroDescanso("Só dá pra descansar numa cidade.")

    custo = cidade.custo_descanso or 0
    if player.ouro < custo:
        raise ErroDescanso(f"Precisa de {custo} Ouro pra descansar aqui.")

    player.ouro -= custo

    from game.corrupcao import modificador_cura_corrupcao, estagio_corrupcao
    mod_cura = modificador_cura_corrupcao(player)
    hp_max = player.hp_max or 24
    hp_atual = player.hp_atual or 1
    hp_faltando = max(0, hp_max - hp_atual)
    hp_recuperado = round(hp_faltando * mod_cura)
    player.hp_atual = min(hp_max, hp_atual + hp_recuperado)

    player.vig_atual = player.vig_max or 60

    estagio = estagio_corrupcao(player.corrupcao or 0)
    if estagio >= 3:
        import random
        d20 = random.randint(1, 20)
        if d20 < 10:
            player.hp_atual = max(1, player.hp_atual - 5)
        else:
            if player.mana_max:
                player.mana_atual = player.mana_max
    else:
        if player.mana_max:
            player.mana_atual = player.mana_max

    session.commit()
    return custo
