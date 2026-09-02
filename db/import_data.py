"""
Importa os dados de data/game_data.json pro banco de dados.

Diferente da versão antiga, essa NÃO precisa da planilha nem do openpyxl —
o JSON já vem pronto dentro do repositório. É chamado automaticamente pelo
bot.py na primeira vez que ele liga (se o banco estiver vazio), então o
usuário não precisa rodar nada na mão.
"""
import json
import os
from sqlalchemy import inspect, text
from db.connection import engine, get_session
from db.models import (
    Base, Tier, CurvaMestra, Classe, TalentoClasse, Arma, Armadura,
    Monstro, Missao, Material, Magia, Local,
)

CAMINHO_JSON = os.path.join(os.path.dirname(__file__), "..", "data", "game_data.json")


def banco_esta_vazio(session):
    return session.query(Tier).count() == 0


def migrar_colunas_novas():
    """
    Sempre que um novo campo é adicionado num modelo (ex: Player.local_atual),
    isso garante que a tabela real no banco ganhe essa coluna também — sem
    precisar mexer no banco na mão toda vez que o jogo cresce.
    """
    inspector = inspect(engine)
    for tabela in Base.metadata.tables.values():
        if not inspector.has_table(tabela.name):
            continue
        colunas_existentes = {c["name"] for c in inspector.get_columns(tabela.name)}
        for coluna in tabela.columns:
            if coluna.name not in colunas_existentes:
                tipo_sql = coluna.type.compile(engine.dialect)
                with engine.begin() as conn:
                    conn.execute(text(
                        f'ALTER TABLE {tabela.name} ADD COLUMN {coluna.name} {tipo_sql}'
                    ))
                    # preenche o valor padrao pra quem ja tinha linha antes da coluna existir
                    if coluna.default is not None and hasattr(coluna.default, "arg"):
                        valor_padrao = coluna.default.arg
                        if not callable(valor_padrao):
                            conn.execute(
                                text(f'UPDATE {tabela.name} SET {coluna.name} = :v WHERE {coluna.name} IS NULL'),
                                {"v": valor_padrao},
                            )
                print(f"Coluna nova adicionada: {tabela.name}.{coluna.name}")


def importar():
    Base.metadata.create_all(engine)
    migrar_colunas_novas()
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
    for item in dados.get("locais", []):
        session.add(Local(**item))

    session.commit()
    session.close()
    print("Importação concluída com sucesso.")


if __name__ == "__main__":
    importar()
