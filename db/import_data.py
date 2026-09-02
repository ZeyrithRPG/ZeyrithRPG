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
                print(f"Coluna nova adicionada: {tabela.name}.{coluna.name}")


def preencher_padroes_faltando():
    """
    Roda SEMPRE, não só quando a coluna é criada.

    Motivo: se uma coluna foi adicionada numa versão anterior do código e ficou
    vazia, ela nunca mais seria preenchida — e o jogo quebraria em quem já tinha
    personagem. Isso varre todas as colunas com valor padrão e preenche o que
    estiver vazio, quantas vezes for preciso. É idempotente: rodar de novo não
    estraga nada nem sobrescreve valor que o jogador já tem.
    """
    inspector = inspect(engine)
    for tabela in Base.metadata.tables.values():
        if not inspector.has_table(tabela.name):
            continue
        colunas_reais = {c["name"] for c in inspector.get_columns(tabela.name)}
        for coluna in tabela.columns:
            if coluna.name not in colunas_reais:
                continue
            if coluna.default is None or not hasattr(coluna.default, "arg"):
                continue
            valor_padrao = coluna.default.arg
            if callable(valor_padrao):
                continue
            with engine.begin() as conn:
                resultado = conn.execute(
                    text(f'UPDATE {tabela.name} SET {coluna.name} = :v WHERE {coluna.name} IS NULL'),
                    {"v": valor_padrao},
                )
                if resultado.rowcount:
                    print(f"Preenchido padrão em {tabela.name}.{coluna.name}: {resultado.rowcount} linha(s)")


def importar():
    Base.metadata.create_all(engine)
    migrar_colunas_novas()
    preencher_padroes_faltando()
    session = get_session()

    tabelas_e_dados = [
        (Tier, "tiers"), (CurvaMestra, "curva_mestra"), (Arma, "armas"),
        (Armadura, "armaduras"), (Monstro, "bestiario"), (Classe, "classes"),
        (TalentoClasse, "talentos_classe"), (Local, "locais"),
    ]

    with open(CAMINHO_JSON, encoding="utf-8") as f:
        dados = json.load(f)

    algo_novo = False
    for Modelo, chave in tabelas_e_dados:
        if session.query(Modelo).count() > 0:
            continue  # essa tabela especifica ja tem dado, nao mexe nela
        for item in dados.get(chave, []):
            session.add(Modelo(**item))
        algo_novo = True
        print(f"Tabela de referência preenchida: {chave}")

    if algo_novo:
        session.commit()
        print("Importação concluída com sucesso.")
    else:
        print("Todas as tabelas de referência já tinham dado — nada novo a importar.")
    session.close()


if __name__ == "__main__":
    importar()
