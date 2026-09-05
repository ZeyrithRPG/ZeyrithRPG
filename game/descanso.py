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
    player.hp_atual = player.hp_max
    player.vig_atual = player.vig_max
    if player.mana_max:
        player.mana_atual = player.mana_max
    session.commit()
    return custo
