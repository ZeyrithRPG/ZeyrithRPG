"""
Eventos de Viagem — flavor narrativo raro durante exploração, filtrado pelo
Ato atual do jogador. Sem efeito mecanico, so imersao.
"""
import random
import re
from game.narrativa import ato_do_nivel

CHANCE_EVENTO = 0.15


def _numeral_romano(ato):
    return ["I", "II", "III", "IV", "V"][ato - 1]


def evento_aleatorio(session, player):
    """Retorna um EventoViagem sorteado (ou None) -- so roda a chance e o filtro,
    nao aplica nada no banco (evento e so narrativo)."""
    if random.random() > CHANCE_EVENTO:
        return None

    from db.models import EventoViagem
    ato = ato_do_nivel(session, player.nivel or 1)
    numeral = _numeral_romano(ato)

    todos = session.query(EventoViagem).all()
    candidatos = [e for e in todos if e.regioes_atos and re.search(rf"Ato[s]? .*\b{numeral}\b", e.regioes_atos)]
    if not candidatos:
        candidatos = todos  # fallback -- nenhum bateu o ato, sorteia de qualquer um
    return random.choice(candidatos) if candidatos else None
