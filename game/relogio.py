"""
Relógio do Mundo — hora_do_mundo (0-23) avança a cada exploração.
Liga direto nas condições "só à noite" que já existiam no Bestiário mas
nunca eram checadas de verdade.
"""
import random

HORA_INICIO_DIA = 6
HORA_INICIO_NOITE = 18

CLIMAS = ["Ensolarado", "Nublado", "Chuvoso", "Tempestade"]
CHANCE_MUDAR_CLIMA = 0.15

ICONE_HORA = {
    "dia": "☀️", "noite": "🌙",
}
ICONE_CLIMA = {
    "Ensolarado": "☀️", "Nublado": "☁️", "Chuvoso": "🌧️", "Tempestade": "⛈️",
}


def eh_noite(hora):
    return hora >= HORA_INICIO_NOITE or hora < HORA_INICIO_DIA


def avancar_tempo(player):
    """Chamado a cada exploracao -- avanca 1 hora, ocasionalmente muda o clima."""
    player.hora_do_mundo = (player.hora_do_mundo + 1) % 24
    if random.random() < CHANCE_MUDAR_CLIMA:
        player.clima_atual = random.choice(CLIMAS)


def periodo_texto(hora):
    return "noite" if eh_noite(hora) else "dia"


def monstro_disponivel_agora(monstro, hora):
    """Checa se a Condicao de Spawn do monstro bate com o periodo atual.
    Se o texto nao menciona dia/noite, esta sempre disponivel."""
    texto = (monstro.condicao_spawn or "").lower()
    if "só à noite" in texto or "so a noite" in texto or "apenas à noite" in texto:
        return eh_noite(hora)
    if "só de dia" in texto or "apenas de dia" in texto or "só durante o dia" in texto:
        return not eh_noite(hora)
    return True
