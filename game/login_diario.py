"""
Login Diário — bônus de Ouro na primeira vez que o jogador abre o bot num dia
novo (data real, não "24h desde o último login"). Sequência quebra se pular
um dia inteiro.
"""
from datetime import date, timedelta

OURO_BASE = 10
OURO_POR_DIA_DE_SEQUENCIA = 5
SEQUENCIA_MAXIMA_PARA_BONUS = 10  # nao cresce pra sempre, capa em 10 dias


def checar_e_aplicar_login(session, player):
    """Retorna (bonus_ouro, novo_streak) se deu bonus hoje, ou None se ja tinha
    logado hoje (evita dar bonus toda vez que abre o bot no mesmo dia)."""
    hoje = date.today()
    hoje_str = hoje.isoformat()

    if player.ultimo_login_data == hoje_str:
        return None  # ja logou hoje, sem bonus de novo

    ontem_str = (hoje - timedelta(days=1)).isoformat()
    if player.ultimo_login_data == ontem_str:
        novo_streak = (player.streak_login or 0) + 1
    else:
        novo_streak = 1  # quebrou a sequencia (ou é o primeiro login)

    streak_p_calculo = min(novo_streak, SEQUENCIA_MAXIMA_PARA_BONUS)
    bonus = OURO_BASE + (streak_p_calculo - 1) * OURO_POR_DIA_DE_SEQUENCIA

    player.ultimo_login_data = hoje_str
    player.streak_login = novo_streak
    player.ouro += bonus
    session.commit()

    return bonus, novo_streak
