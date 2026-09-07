"""
Proficiência de Arma — +1 ponto por hit acertado em combate. Nível sobe numa
curva lenta e crescente (cada nível pede mais que o anterior). O efeito
final (bônus de Dano) depende da AFINIDADE da classe com aquele tipo de
arma: mesma proficiência bruta rende buff diferente pra cada classe.
"""

CUSTO_BASE = 100
MULTIPLICADOR_CURVA = 1.5
NIVEL_MAXIMO_PROFICIENCIA = 30
NIVEL_MAXIMO = NIVEL_MAXIMO_PROFICIENCIA  # Alias para compatibilidade retroativa
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


# =========================================================================
# 4 TRILHAS PASSIVAS UNIVERSAIS (Item 3 do Prompt Mestre Final)
# =========================================================================

def bonus_mult_critico(nivel: int) -> float:
    """A cada 4 níveis: Multiplicador de Crítico +0.05x (base 2.0x, Nv 28 = 2.35x, teto no Nv 30)."""
    nv = min(NIVEL_MAXIMO_PROFICIENCIA, max(0, nivel or 0))
    return round((nv // 4) * 0.05, 4)


def bonus_drop_materiais_pct(nivel: int) -> float:
    """A cada 3 níveis: +1% de Chance de Drop de materiais (injetado no hit letal)."""
    nv = min(NIVEL_MAXIMO_PROFICIENCIA, max(0, nivel or 0))
    return round((nv // 3) * 1.0, 4)


def bonus_critico_chance_pct(nivel: int) -> float:
    """A cada 5 níveis: +0.5% de Chance de Crítico base em calcular_critico_chance()."""
    nv = min(NIVEL_MAXIMO_PROFICIENCIA, max(0, nivel or 0))
    return round((nv // 5) * 0.5, 4)


def bonus_desconto_reparo_pct(nivel: int) -> float:
    """A cada 6 níveis: -2% no custo de reparo dessa arma no ferreiro."""
    nv = min(NIVEL_MAXIMO_PROFICIENCIA, max(0, nivel or 0))
    return round((nv // 6) * 0.02, 4)


def obter_trilhas_desbloqueadas_nivel(nivel: int) -> list[str]:
    """Retorna apenas as trilhas passivas que ganharam bônus neste nível específico (Item 11.3)."""
    trilhas = []
    if nivel > 0:
        if nivel % 4 == 0:
            trilhas.append("💥 +0.05x Dano Crítico")
        if nivel % 3 == 0:
            trilhas.append("🎲 +1% Chance de Drop")
        if nivel % 5 == 0:
            trilhas.append("🎯 +0.5% Chance de Crítico")
        if nivel % 6 == 0:
            trilhas.append("🔧 -2% custo de Reparo")
    return trilhas



def custo_do_nivel(nivel):
    """Custo EM PONTOS pra sair do nivel (nivel-1) pro nivel. Nivel 1->2 = 100."""
    return round(CUSTO_BASE * (MULTIPLICADOR_CURVA ** (nivel - 1)))


def nivel_e_progresso(pontos_totais):
    """Retorna (nivel_atual, pontos_no_nivel_atual, pontos_pro_proximo_nivel)."""
    nivel = 0
    restante = pontos_totais
    while nivel < NIVEL_MAXIMO_PROFICIENCIA:
        custo = custo_do_nivel(nivel + 1)
        if restante < custo:
            return nivel, restante, custo
        restante -= custo
        nivel += 1
    return NIVEL_MAXIMO_PROFICIENCIA, 0, 0  # no maximo, nao pede mais nada


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
