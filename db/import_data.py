"""
Importa os dados de data/game_data.json pro banco de dados.

Diferente da versão antiga, essa NÃO precisa da planilha nem do openpyxl —
o JSON já vem pronto dentro do repositório. É chamado automaticamente pelo
bot.py na primeira vez que ele liga (se o banco estiver vazio), então o
usuário não precisa rodar nada na mão.
"""
import json
import os
from db.connection import engine, get_session
from db.models import (
    Base, Tier, CurvaMestra, Classe, TalentoClasse, Arma, Armadura,
    Monstro, Missao, Material, Magia,
)

CAMINHO_JSON = os.path.join(os.path.dirname(__file__), "..", "data", "game_data.json")


def banco_esta_vazio(session):
    return session.query(Tier).count() == 0


def importar():
    Base.metadata.create_all(engine)
    session = get_session()

    if not banco_esta_vazio(session):
        session.close()
        print("Banco já tem dados de referência — importação pulada.")
        return

    with open(CAMINHO_JSON, encoding="utf-8") as f:
        dados = json.load(f)

    for item in dados.get("tiers", []):
        session.add(Tier(**item))
    for item in dados.get("curva_mestra", []):
        session.add(CurvaMestra(**item))
    for item in dados.get("armas", []):
        session.add(Arma(**item))
    for item in dados.get("armaduras", []):
        session.add(Armadura(**item))
    for item in dados.get("bestiario", []):
        session.add(Monstro(**item))
    for item in dados.get("classes", []):
        session.add(Classe(**item))
    for item in dados.get("talentos_classe", []):
        session.add(TalentoClasse(**item))

    session.commit()
    session.close()
    print("Importação concluída com sucesso.")


if __name__ == "__main__":
    importar()
