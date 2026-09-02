"""
Combate — usa a fórmula original do jogo: d20 + BônusAtaque >= Defesa do alvo.
Natural 1 sempre erra. Natural 20 sempre acerta e causa dano em dobro (crítico).
"""
import random
from dataclasses import dataclass


@dataclass
class ResultadoAtaque:
    acertou: bool
    critico: bool
    dano: int
    rolagem: int


def resolver_ataque(atq_bonus: int, defesa_alvo: int, dano_base: int) -> ResultadoAtaque:
    d20 = random.randint(1, 20)

    if d20 == 1:
        return ResultadoAtaque(acertou=False, critico=False, dano=0, rolagem=d20)

    critico = d20 == 20
    acertou = critico or (d20 + atq_bonus) >= defesa_alvo

    if not acertou:
        return ResultadoAtaque(acertou=False, critico=False, dano=0, rolagem=d20)

    dano = dano_base * 2 if critico else dano_base
    return ResultadoAtaque(acertou=True, critico=critico, dano=dano, rolagem=d20)


def chance_fuga(bonus: int = 10) -> bool:
    """40% base + 5% por ponto de atributo. Sem ficha de atributos ainda, usa um valor fixo moderado."""
    chance = 0.40 + (bonus * 0.005)
    return random.random() < min(chance, 0.90)
