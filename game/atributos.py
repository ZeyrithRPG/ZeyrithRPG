"""
Atributos base (FOR/DES/CON/INT/SAB/CAR) — por ora DECORATIVO, não afeta
nenhuma conta de combate (isso já foi decidido e vai continuar assim até
o sistema de distribuição manual de pontos ser implementado).
"""
import re

CHAVE_PARA_CAMPO = {
    "FOR": "atributo_for", "DES": "atributo_des", "CON": "atributo_con",
    "INT": "atributo_int", "SAB": "atributo_sab", "CAR": "atributo_car",
}

VALOR_PRIMARIO = 14
VALOR_SECUNDARIO = 12
VALOR_BASE = 10


def _parse_atributos_primario_secundario(texto):
    """'FOR & SAB (Primários) / CON (Secundário)' -> ({'FOR','SAB'}, {'CON'})"""
    primarios, secundarios = set(), set()
    if not texto:
        return primarios, secundarios
    partes = texto.split("/")
    for parte in partes:
        chaves = re.findall(r"[A-Z]{3}", parte)
        if "rimári" in parte or "rimario" in parte.lower():
            primarios.update(chaves)
        elif "ecundári" in parte or "ecundario" in parte.lower():
            secundarios.update(chaves)
    return primarios, secundarios


def calcular_atributos_iniciais(classe):
    """Retorna um dict pronto pra jogar em setattr(player, campo, valor)."""
    valores = {campo: VALOR_BASE for campo in CHAVE_PARA_CAMPO.values()}
    if not classe or not classe.atributo_primario:
        return valores

    primarios, secundarios = _parse_atributos_primario_secundario(classe.atributo_primario)
    for chave in primarios:
        if chave in CHAVE_PARA_CAMPO:
            valores[CHAVE_PARA_CAMPO[chave]] = VALOR_PRIMARIO
    for chave in secundarios:
        campo = CHAVE_PARA_CAMPO.get(chave)
        if campo and valores[campo] == VALOR_BASE:  # nao sobrescreve um Primario
            valores[campo] = VALOR_SECUNDARIO
    return valores


def aplicar_atributos_iniciais(player, classe):
    for campo, valor in calcular_atributos_iniciais(classe).items():
        setattr(player, campo, valor)


def player_precisa_de_atributos(player):
    """Detecta personagem antigo, criado antes desse sistema existir --
    todos os 6 campos ainda no valor padrao de fabrica (10) apesar de ja ter classe."""
    return (
        player.classe_id is not None
        and player.atributo_for == 10 and player.atributo_des == 10
        and player.atributo_con == 10 and player.atributo_int == 10
        and player.atributo_sab == 10 and player.atributo_car == 10
    )
