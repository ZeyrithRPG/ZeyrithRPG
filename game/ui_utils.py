"""
Utilidades visuais compartilhadas — usadas por todos os handlers, pra manter
o HUD, o Mapa e o Combate com a mesma barra, sempre.
"""


def barra(atual, maximo, tamanho=10, cheio="🟩", vazio="⬛"):
    if not maximo:
        return vazio * tamanho
    n = round(tamanho * max(0, min(atual, maximo)) / maximo)
    return cheio * n + vazio * (tamanho - n)
