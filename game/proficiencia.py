"""
Proficiência de Arma — +1 ponto por hit acertado em combate. Nível sobe numa
curva lenta e crescente (cada nível pede mais que o anterior). O efeito
final (bônus de Dano) depende da AFINIDADE da classe com aquele tipo de
arma: mesma proficiência bruta rende buff diferente pra cada classe.
"""

CUSTO_BASE = 100
MULTIPLICADOR_CURVA = 1.5
NIVEL_MAXIMO = 20
BONUS_DANO_POR_NIVEL_AFINADA = 0.01  # 1% de dano por nivel, na arma afinada

AFINIDADE = {
    "Guerreiro da Forja": {"afinada": ["Espada", "Machado", "Maca", "Manopla"], "neutra": ["Adaga"]},
    "Inquisidor de Prata": {"afinada": ["Espada", "Maca"], "neutra": ["Machado", "Manopla"]},
    "Conjurador de Sangue (Hemomante)": {"afinada": ["Cetro", "Adaga"], "neutra": ["Espada"]},
    "Batedor dos Ecos": {"afinada": ["Arco", "Adaga"], "neutra": ["Espada"]},
    "Ladino das Sombras": {"afinada": ["Adaga", "Arco"], "neutra": ["Espada"]},
    "Mago Elemental": {"afinada": ["Cetro"], "neutra": ["Adaga"]},
    "Bárbaro da Fenda": {"afinada": ["Machado", "Maca", "Manopla"], "neutra": ["Espada"]},
    "Artífice Mecânico": {"afinada": ["Arco", "Manopla"], "neutra": ["Adaga", "Espada"]},
}


def custo_do_nivel(nivel):
    """Custo EM PONTOS pra sair do nivel (nivel-1) pro nivel. Nivel 1->2 = 100."""
    return round(CUSTO_BASE * (MULTIPLICADOR_CURVA ** (nivel - 1)))


def nivel_e_progresso(pontos_totais):
    """Retorna (nivel_atual, pontos_no_nivel_atual, pontos_pro_proximo_nivel)."""
    nivel = 0
    restante = pontos_totais
    while nivel < NIVEL_MAXIMO:
        custo = custo_do_nivel(nivel + 1)
        if restante < custo:
            return nivel, restante, custo
        restante -= custo
        nivel += 1
    return NIVEL_MAXIMO, 0, 0  # no maximo, nao pede mais nada


def _afinidade_classe(nome_classe, tipo_arma):
    dados = AFINIDADE.get(nome_classe)
    if not dados:
        return "neutra"
    if tipo_arma in dados.get("afinada", []):
        return "afinada"
    if tipo_arma in dados.get("neutra", []):
        return "neutra"
    return "desafinada"


def bonus_dano_percentual(nivel, nome_classe, tipo_arma):
    afinidade = _afinidade_classe(nome_classe, tipo_arma)
    multiplicador = {"afinada": 1.0, "neutra": 0.5, "desafinada": 0.25}[afinidade]
    return nivel * BONUS_DANO_POR_NIVEL_AFINADA * multiplicador


def registrar_hit(session, player, tipo_arma):
    """Chamado a cada hit que acerta em combate. Retorna (subiu_de_nivel, nivel_novo)."""
    from db.models import PlayerProficiencia

    reg = (
        session.query(PlayerProficiencia)
        .filter_by(player_id=player.id, tipo_arma=tipo_arma)
        .first()
    )
    if not reg:
        reg = PlayerProficiencia(player_id=player.id, tipo_arma=tipo_arma, valor=0)
        session.add(reg)

    nivel_antes, _, _ = nivel_e_progresso(reg.valor)
    reg.valor += 1
    nivel_depois, _, _ = nivel_e_progresso(reg.valor)
    session.commit()

    return (nivel_depois > nivel_antes), nivel_depois
