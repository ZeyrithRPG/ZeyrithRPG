"""
Fase 6 — Mapa: locais visiveis (respeitando Secreto), viajar, Covil de Boss.
"""
import re


def _monstros_do_gatilho_secreto(descricao_local):
    """'Só revelado se a Criança Marcada ou o Batedor Ferido em Fuga forem poupados.'
    -> ['Criança Marcada', 'Batedor Ferido em Fuga']"""
    if not descricao_local:
        return []
    m = re.search(r"se (.+?) (?:for|forem) poupad", descricao_local, re.IGNORECASE)
    if not m:
        return []
    nomes = [n.strip() for n in m.group(1).split(" ou ")]
    return [re.sub(r"^(a|o|à|ao)\s+", "", n, flags=re.IGNORECASE) for n in nomes]


def local_esta_desbloqueado(local, player):
    if local.tipo != "Local Secreto":
        return True
    gatilhos = _monstros_do_gatilho_secreto(local.descricao)
    poupados = (player.monstros_poupados or "").split("|")
    return any(g in poupados for g in gatilhos)


def listar_locais_visiveis(session, player, tier_nome_atual=None):
    from db.models import Local

    todos = session.query(Local).order_by(Local.id).all()
    visiveis = []
    for local in todos:
        if not local_esta_desbloqueado(local, player):
            continue
        # local muito acima do nivel do jogador fica visivel mas travado (nao escondido)
        local.travado = bool(local.nivel_ref and player.nivel and local.nivel_ref > (player.nivel + 15))
        visiveis.append(local)
    return visiveis


def cidade_polo_do_local(session, nome_local):
    """Resolve qual Cidade Polo 'pertence' a um local qualquer (por nome).
    Usa Cidade.pontos_interesse como fonte de verdade (lista todos os locais do polo),
    normalizando acento pra evitar o problema conhecido de nomes divergentes entre abas
    (ex: 'cidade_proxima' do Local às vezes traz 'Valória', às vezes 'Vila Inicial',
    às vezes nem é uma cidade, é outro local do mesmo polo)."""
    from db.models import Cidade
    from game.economia import _normalizar

    alvo = _normalizar(nome_local)
    if not alvo:
        return None
    for cidade in session.query(Cidade).all():
        candidatos = [cidade.nome]
        if cidade.nome_oficial:
            candidatos.append(cidade.nome_oficial.split(" (")[0].strip())
        if any(_normalizar(c) == alvo for c in candidatos):
            return cidade
        pontos = [p.strip() for p in (cidade.pontos_interesse or "").split(",")]
        if any(_normalizar(p) == alvo for p in pontos):
            return cidade
    return None


def _nomes_monstros(o_que_tem):
    """'Javali Selvagem Alfa (exclusivo), Leitão Marcado' -> ['Javali Selvagem Alfa', 'Leitão Marcado']
    Remove os parenteses ANTES de separar por virgula, porque alguns tem virgula
    dentro (ex: 'Barão Aldous Grimm (Corrompido, exclusivo)') e cortar por virgula
    primeiro quebra esse nome em pedacos errados."""
    if not o_que_tem:
        return []
    sem_parenteses = re.sub(r"\([^)]*\)", "", o_que_tem)
    nomes = []
    for parte in sem_parenteses.split(","):
        limpo = parte.strip()
        if limpo and limpo.lower() not in ("nenhum monstro", "nenhum"):
            nomes.append(limpo)
    return nomes


def local_da_cidade(session, cidade):
    """Acha o Local[tipo=Cidade] correspondente, tolerando o acento divergente
    conhecido entre Cidade.nome (sem acento, ex 'Entreposto Elfico') e
    Local.nome (com acento, ex 'Entreposto Élfico')."""
    from db.models import Local
    from game.economia import _normalizar

    local = session.query(Local).filter_by(nome=cidade.nome).first()
    if local:
        return local
    alvo = _normalizar(cidade.nome)
    for candidato in session.query(Local).filter_by(tipo="Cidade").all():
        if _normalizar(candidato.nome) == alvo:
            return candidato
    return None


def locais_do_polo(session, cidade):
    """Todos os Locais de um Polo, na ordem da planilha (Cidade.pontos_interesse)."""
    from db.models import Local

    nomes = [p.strip() for p in (cidade.pontos_interesse or "").split(",") if p.strip()]
    locais = []
    for nome in nomes:
        local = session.query(Local).filter_by(nome=nome).first()
        if local:
            locais.append(local)
    return locais


def local_mae_do_covil(covil, locais_do_polo):
    """Acha qual local 'normal' (nao Covil) do mesmo polo deu origem ao Covil de Boss,
    cruzando os monstros de o_que_tem (o Covil e o local-mae sempre compartilham
    pelo menos 1 monstro, ex: Covil do Javali Alfa <-> Bosque Sombrio compartilham
    'Javali Selvagem Alfa')."""
    from game.economia import _normalizar

    nomes_covil = {_normalizar(n) for n in _nomes_monstros(covil.o_que_tem)}
    if not nomes_covil:
        return None
    for outro in locais_do_polo:
        if outro.id == covil.id or outro.tipo == "Covil de Boss":
            continue
        nomes_outro = {_normalizar(n) for n in _nomes_monstros(outro.o_que_tem)}
        if nomes_covil & nomes_outro:
            return outro
    return None


def covil_esta_descoberto(covil, player, locais_do_polo):
    """Um Covil de Boss só aparece no Mapa Regional depois que o jogador
    explorou pelo menos 1x o local-mãe onde o boss 'mora'. Quando a planilha
    não deixa identificar esse local-mãe (nenhum monstro em comum com um
    vizinho), cai num fallback por nível: revela quando o jogador chega perto
    o suficiente do nível do Covil, pra ainda ter alguma progressão em vez de
    aparecer sempre desde o Nível 1."""
    mae = local_mae_do_covil(covil, locais_do_polo)
    if mae is None:
        return bool(player.nivel and covil.nivel_ref and player.nivel >= covil.nivel_ref - 2)
    visitados = (player.locais_visitados or "").split("|")
    return mae.nome in visitados


def boss_e_local_do_portao(session, cidade):
    """O Boss do Portao Regional e o ULTIMO Covil de Boss do polo, na ordem
    da planilha, antes da proxima Cidade Polo (ex: no Polo I isso e a
    Camara do Barao / Barao Aldous Grimm -- bate com o mockup aprovado)."""
    locais = locais_do_polo(session, cidade)
    covis = [l for l in locais if l.tipo == "Covil de Boss"]
    if not covis:
        return None, None
    covil_portao = covis[-1]
    boss = monstro_do_covil(session, covil_portao)
    return boss, covil_portao


def _boss_foi_derrotado(player, boss):
    from game.economia import _normalizar
    if not boss:
        return False
    derrotados = (player.bosses_derrotados or "").split("|")
    return any(_normalizar(d) == _normalizar(boss.nome) for d in derrotados)


def proxima_cidade(session, cidade_atual):
    from db.models import Cidade
    return session.query(Cidade).filter(Cidade.id > cidade_atual.id).order_by(Cidade.id).first()


def portao_liberado(session, player, cidade_atual):
    """Se True, o jogador ja pode atravessar pro proximo Polo.
    Nivel exigido = o nivel_ref do proprio Local[tipo=Cidade] da proxima cidade
    (o mesmo numero que aparece na tela pro jogador, pra nao ter placa dizendo
    uma coisa e codigo cobrando outra)."""
    from db.models import Local

    proxima = proxima_cidade(session, cidade_atual)
    if not proxima:
        return True, None  # ultimo polo, nao tem portao
    boss, _covil = boss_e_local_do_portao(session, cidade_atual)
    local_proxima = local_da_cidade(session, proxima)
    nivel_exigido = (local_proxima.nivel_ref if local_proxima else proxima.nivel_min) or 1
    nivel_ok = (player.nivel or 1) >= nivel_exigido
    boss_ok = _boss_foi_derrotado(player, boss)
    return (nivel_ok and boss_ok), proxima


def cidades_em_ordem(session):
    from db.models import Cidade
    return session.query(Cidade).order_by(Cidade.id).all()


def cidades_desbloqueadas(session, player):
    """Retorna lista de (cidade, desbloqueada) em ordem -- a Polo I sempre comeca
    liberada, as seguintes so liberam em cascata (precisa ter passado pelo portao
    de todas as anteriores)."""
    resultado = []
    liberada_anterior = True
    for cidade in cidades_em_ordem(session):
        resultado.append((cidade, liberada_anterior))
        if liberada_anterior:
            liberada_anterior, _ = portao_liberado(session, player, cidade)
    return resultado


def monstro_do_covil(session, local):
    """Pega o(s) nome(s) exclusivo(s) do Covil de Boss a partir do campo o_que_tem,
    e retorna o Monstro real correspondente (o primeiro que achar no banco)."""
    from db.models import Monstro

    if local.tipo != "Covil de Boss" or not local.o_que_tem:
        return None

    nomes_candidatos = [n.strip() for n in local.o_que_tem.split(",")]
    for candidato in nomes_candidatos:
        nome_limpo = re.sub(r"\s*\(exclusivo\)\s*", "", candidato).strip()
        monstro = session.query(Monstro).filter(Monstro.nome.like(f"{nome_limpo}%")).first()
        if monstro:
            return monstro
    return None
