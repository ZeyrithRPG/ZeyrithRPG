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
    Monstro, Missao, Material, Magia, Local, Receita, Titulo,
)
import re

import hashlib

_CAMPOS_MISSAO = {c.name for c in Missao.__table__.columns}
_CAMPOS_MATERIAL = {c.name for c in Material.__table__.columns}
_CAMPOS_LOCAL = {c.name for c in Local.__table__.columns}


def _hash_lista(itens):
    bruto = json.dumps(itens, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(bruto.encode("utf-8")).hexdigest()[:16]


def _hash_salvo_path():
    return os.path.join(os.path.dirname(__file__), "..", "data", "_ultimo_hash_importado.json")


def _texto_pra_numero(valor):
    """Recompensa/preco na planilha as vezes vem como texto tipo '144 Ouro' -- extrai o numero."""
    if isinstance(valor, (int, float)) or valor is None:
        return valor
    m = re.search(r"-?\d+", str(valor))
    return int(m.group()) if m else None

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
        colunas_existentes = {c["name"]: c for c in inspector.get_columns(tabela.name)}
        for coluna in tabela.columns:
            if coluna.name not in colunas_existentes:
                tipo_sql = coluna.type.compile(engine.dialect)
                with engine.begin() as conn:
                    conn.execute(text(
                        f'ALTER TABLE {tabela.name} ADD COLUMN {coluna.name} {tipo_sql}'
                    ))
                print(f"Coluna nova adicionada: {tabela.name}.{coluna.name}")
                continue

            # coluna ja existe -- confere se o TIPO bate com o modelo atual.
            # So corrige a direcao segura (banco mais estreito que o modelo quer,
            # ex: Integer quando o modelo pede Text) -- qualquer int cabe em texto
            # sem perda. Nunca estreita (Text -> Integer) sozinho, isso pode falhar
            # com dado real e precisa de decisao humana.
            tipo_real = colunas_existentes[coluna.name]["type"]
            modelo_quer_text = str(coluna.type).upper() in ("TEXT", "VARCHAR")
            banco_tem_numero = "INT" in str(tipo_real).upper() or "NUMERIC" in str(tipo_real).upper()
            if modelo_quer_text and banco_tem_numero and engine.dialect.name == "postgresql":
                with engine.begin() as conn:
                    conn.execute(text(
                        f'ALTER TABLE {tabela.name} ALTER COLUMN {coluna.name} TYPE TEXT USING {coluna.name}::TEXT'
                    ))
                print(f"Tipo de coluna corrigido: {tabela.name}.{coluna.name} ({tipo_real} -> TEXT)")


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
        (TalentoClasse, "talentos_classe"), (Local, "locais"), (Magia, "magias"),
        (Missao, "missoes"), (Material, "materiais"), (Receita, "receitas"),
        (Titulo, "titulos"),
    ]

    with open(CAMINHO_JSON, encoding="utf-8") as f:
        dados = json.load(f)

    hashes_salvos = {}
    if os.path.exists(_hash_salvo_path()):
        with open(_hash_salvo_path(), encoding="utf-8") as f:
            hashes_salvos = json.load(f)

    novos_hashes = dict(hashes_salvos)
    algo_novo = False
    for Modelo, chave in tabelas_e_dados:
        itens_json = dados.get(chave, [])
        hash_atual = _hash_lista(itens_json)
        if hashes_salvos.get(chave) == hash_atual and session.query(Modelo).count() > 0:
            continue  # conteudo identico ao ultimo import, nao mexe
        # Tabela de REFERENCIA (nunca escrita durante o jogo) — seguro substituir por completo
        # sempre que a planilha mudar (rebalanceamento), detectado por hash de conteudo.
        qtd_antes = session.query(Modelo).count()
        session.query(Modelo).delete()
        campos_validos = {c.name for c in Modelo.__table__.columns}
        for item in itens_json:
            item_limpo = {k: v for k, v in item.items() if k in campos_validos}
            if "preco_base" in item_limpo:
                item_limpo["preco_base"] = _texto_pra_numero(item_limpo["preco_base"])
            # SQLAlchemy 2.0 se confunde ao inserir em lote quando a MESMA coluna Text
            # recebe tipo Python misto (int numa linha, str noutra) -- normaliza pra
            # sempre string em qualquer campo que o modelo declara como Text/String
            # mas que pode vir como numero da planilha (ex: recompensa).
            for campo, valor in list(item_limpo.items()):
                if valor is not None and not isinstance(valor, (str, bool)):
                    coluna_modelo = Modelo.__table__.columns.get(campo)
                    if coluna_modelo is not None and str(coluna_modelo.type).upper() in ("TEXT", "VARCHAR"):
                        item_limpo[campo] = str(valor)
            session.add(Modelo(**item_limpo))
        novos_hashes[chave] = hash_atual
        algo_novo = True
        print(f"Tabela de referência sincronizada: {chave} ({qtd_antes} -> {len(itens_json)})")

    if algo_novo:
        os.makedirs(os.path.dirname(_hash_salvo_path()), exist_ok=True)
        with open(_hash_salvo_path(), "w", encoding="utf-8") as f:
            json.dump(novos_hashes, f)

    if algo_novo:
        session.commit()
        print("Importação concluída com sucesso.")
    else:
        print("Todas as tabelas de referência já tinham dado — nada novo a importar.")
    session.close()


if __name__ == "__main__":
    importar()
