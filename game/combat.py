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


PONTOS_INFECCAO_POR_PAPEL = {"Comum": 2, "Elite": 3, "Boss": 5, "Cosmico": 5}

FRASE_DERROTA_POR_TIPO = {
    "Estrada Perigosa": "Viajantes encontraram seu corpo estirado na poeira e o arrastaram até os portões da cidade. Seus bolsos foram revirados pelo caminho.",
    "Campo de Batalha": "Viajantes encontraram seu corpo estirado na poeira e o arrastaram até os portões da cidade. Seus bolsos foram revirados pelo caminho.",
    "Floresta Perigosa": "O sangue negro da fera atingiu suas feridas abertas. Caçadores o resgataram antes que a podridão tomasse conta do restante do seu corpo.",
    "Pantano": "O sangue negro da fera atingiu suas feridas abertas. Caçadores o resgataram antes que a podridão tomasse conta do restante do seu corpo.",
    "Mina": "Mineiros retiraram seus ossos quebrados do fundo das galerias escuras. O ar tóxico e a poeira de pedra ainda queimam em seus pulmões.",
    "Caverna": "Mineiros retiraram seus ossos quebrados do fundo das galerias escuras. O ar tóxico e a poeira de pedra ainda queimam em seus pulmões.",
    "Dungeon": "O eco dos corredores de pedra foi a última coisa que você ouviu antes de apagar. Saqueadores o deixaram nos degraus da cidade em troca de algumas moedas.",
    "Ruina": "O eco dos corredores de pedra foi a última coisa que você ouviu antes de apagar. Saqueadores o deixaram nos degraus da cidade em troca de algumas moedas.",
    "Covil de Boss": "A presença esmagadora do monstro partiu seu espírito. A marca carmesim arde sob sua carne como fogo vivo enquanto você acorda febril na estalagem.",
    "Fenda": "A presença esmagadora do monstro partiu seu espírito. A marca carmesim arde sob sua carne como fogo vivo enquanto você acorda febril na estalagem.",
}
FRASE_DERROTA_PADRAO = "Alguém o encontrou desacordado e o trouxe de volta à cidade, mais vivo do que deveria."


def frase_derrota_por_tipo_local(tipo_local):
    return FRASE_DERROTA_POR_TIPO.get(tipo_local, FRASE_DERROTA_PADRAO)


def resolver_derrota(player_ouro, player_corrupcao, player_hora_do_mundo, monstro_papel, tipo_local_atual):
    """Calcula as consequencias puras da derrota (sem tocar em Telegram/sessao),
    pra poder testar isolado e reaproveitar. Retorna um dict pronto pra aplicar no Player."""
    pontos_infeccao = PONTOS_INFECCAO_POR_PAPEL.get(monstro_papel, 2)
    ouro_perdido = int((player_ouro or 0) * 0.10)
    return {
        "pontos_infeccao": pontos_infeccao,
        "corrupcao_nova": min(100, (player_corrupcao or 0) + pontos_infeccao),
        "ouro_perdido": ouro_perdido,
        "ouro_novo": (player_ouro or 0) - ouro_perdido,
        "hora_nova": ((player_hora_do_mundo or 0) + 4) % 24,
        "frase_narrativa": frase_derrota_por_tipo_local(tipo_local_atual),
    }


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
