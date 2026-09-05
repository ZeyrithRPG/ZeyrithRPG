"""
Combate — usa a fórmula original do jogo: d20 + BônusAtaque >= Defesa do alvo.
Natural 1 sempre erra. Natural 20 sempre acerta e causa dano em dobro (crítico).
"""
import random
import re
from dataclasses import dataclass


@dataclass
class ResultadoAtaque:
    acertou: bool
    critico: bool
    dano: int
    rolagem: int


def resolver_ataque(atq_bonus: int, defesa_alvo: int, dano_base: int, bonus_critico_pct: int = 0) -> ResultadoAtaque:
    d20 = random.randint(1, 20)

    if d20 == 1:
        return ResultadoAtaque(acertou=False, critico=False, dano=0, rolagem=d20)

    critico = d20 == 20 or (bonus_critico_pct > 0 and random.random() < bonus_critico_pct / 100)
    acertou = critico or (d20 + atq_bonus) >= defesa_alvo

    if not acertou:
        return ResultadoAtaque(acertou=False, critico=False, dano=0, rolagem=d20)

    dano = dano_base * 2 if critico else dano_base
    return ResultadoAtaque(acertou=True, critico=critico, dano=dano, rolagem=d20)


def chance_fuga(bonus: int = 10) -> bool:
    """40% base + 5% por ponto de atributo. Sem ficha de atributos ainda, usa um valor fixo moderado."""
    chance = 0.40 + (bonus * 0.005)
    return random.random() < min(chance, 0.90)


def verificar_pode_poupar(monstro, hp_atual_monstro, hp_max_monstro):
    """
    Retorna True se o jogador pode poupar esse monstro agora, baseado em:
    - Papel de Combate = Nao-hostil (pode poupar desde o inicio)
    - Interacao Ambiental menciona 'rende-se a X% de HP' e ja chegou nesse ponto
    """
    if not monstro.papel_combate:
        return False
    papel = monstro.papel_combate.lower().replace("ã", "a")
    if "nao-hostil" in papel or "nao hostil" in papel:
        return True

    texto = (monstro.interacao_ambiental or "")
    m = re.search(r"(\d+)%\s*(de\s*)?hp", texto, re.IGNORECASE)
    if m and hp_max_monstro:
        limite_pct = int(m.group(1))
        hp_pct_atual = (hp_atual_monstro / hp_max_monstro) * 100
        return hp_pct_atual <= limite_pct
    return False
