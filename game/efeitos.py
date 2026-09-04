"""
Os 10 Efeitos — regra numérica fixa, exatamente como fechamos na Seção 8
da planilha. Aplicados por golpe, tickam a cada turno.
"""
import re

REGRA_EFEITO = {
    "Sangramento": {"dano_por_turno": 1, "turnos": 2},
    "Queimadura": {"dano_por_turno": 2, "turnos": 2},
    "Veneno": {"dano_por_turno": 1, "turnos": 2},
    "Atordoamento": {"chance": 0.20, "turnos": 1},
    "Lentidão": {"turnos": 1},
}

# tenta reconhecer o efeito a partir do texto livre do Golpe/Efeito Mecânico do monstro
PALAVRAS_CHAVE = {
    "Sangramento": ["sangr"],
    "Queimadura": ["queima", "fogo", "chama", "incandesc"],
    "Veneno": ["veneno", "peçonh"],
    "Atordoamento": ["atordo"],
    "Lentidão": ["imobiliz", "lent"],
}


def identificar_efeito(texto: str):
    """Devolve o nome do efeito reconhecido no texto, ou None."""
    if not texto:
        return None
    texto_lower = texto.lower()
    for efeito, palavras in PALAVRAS_CHAVE.items():
        if any(p in texto_lower for p in palavras):
            return efeito
    return None


def aplicar_dano_periodico(nome_efeito: str) -> int:
    regra = REGRA_EFEITO.get(nome_efeito, {})
    return regra.get("dano_por_turno", 0)


def turnos_padrao(nome_efeito: str) -> int:
    return REGRA_EFEITO.get(nome_efeito, {}).get("turnos", 1)


ICONE_EFEITO = {
    "Sangramento": "🩸", "Queimadura": "🔥", "Veneno": "☠️",
    "Atordoamento": "💫", "Lentidão": "🐌",
}
