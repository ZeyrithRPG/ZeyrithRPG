"""
Exploração — reaproveita a tabela de Perigo do Bloco 3 e o custo de VIG do
Sistema de Tempo, exatamente como fechamos na planilha.
"""
import random

# Bandas do d100 por Perigo (Nada / Comum / Elite / AmeaçaSup / Boss / Achado)
# "nada" reduzido pela metade em relacao ao original -- 70% de chance de nada
# em Perigo 1 estava gastando 70-80% do Vigor do jogador so pra achar 1 monstro.
TABELA_PERIGO = {
    1: {"nada": 35, "comum": 90, "elite": 97, "ameaca_sup": 99, "boss": 99},
    2: {"nada": 30, "comum": 83, "elite": 94, "ameaca_sup": 98, "boss": 99},
    3: {"nada": 25, "comum": 75, "elite": 87, "ameaca_sup": 95, "boss": 99},
    4: {"nada": 18, "comum": 63, "elite": 80, "ameaca_sup": 93, "boss": 99},
    5: {"nada": 10, "comum": 45, "elite": 65, "ameaca_sup": 85, "boss": 97},
}


def custo_vig_exploracao(perigo: int) -> int:
    return 5 + max(0, perigo - 1)


def rolar_exploracao(perigo: int) -> str:
    """Retorna: 'nada' | 'comum' | 'elite' | 'ameaca_sup' | 'boss' | 'achado'"""
    banda = TABELA_PERIGO.get(perigo, TABELA_PERIGO[3])
    d100 = random.randint(1, 100)
    if d100 <= banda["nada"]:
        return "nada"
    if d100 <= banda["comum"]:
        return "comum"
    if d100 <= banda["elite"]:
        return "elite"
    if d100 <= banda["ameaca_sup"]:
        return "ameaca_sup"
    if d100 <= banda["boss"]:
        return "boss"
    return "achado"
