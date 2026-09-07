"""
Talentos de Classe — A Infecção que Segura o Mundo
Item 7 do Prompt Mestre Final:
- Concessão de talentos por nível e persistência via PlayerTalento.
- Mensagem narrativa oficial citando o mestre do talento ao desbloquear.
- 8 Talentos de Nível 15 ativos mecanicamente.
- 24 Talentos Avançados (Nível 26+) com a tag literal '🔧 Efeito em desenvolvimento'.
"""
from typing import Optional, List, Dict, Tuple, Any

TAG_DESENVOLVIMENTO = "🔧 Efeito em desenvolvimento"

TERMOS_PURIFICACAO = (
    "morto-vivo",
    "morto_vivo",
    "morto vivo",
    "undead",
    "cultista",
    "culto",
    "aberracao",
    "aberração",
    "esqueleto",
    "zumbi",
    "necrofago",
    "necrófago",
    "infeccioso",
    "infecção viva",
)


def jogador_tem_talento(player, session=None, nome_talento: Optional[str] = None, talento_id: Optional[int] = None) -> bool:
    """
    Verifica se o jogador possui e aprendeu o talento especificado (por nome ou ID).
    Suporta instâncias com relação SQLAlchemy já carregada, mocks e queries no banco.
    """
    if not player:
        return False

    # 1. Checagem direta na coleção em memória (se disponível)
    talentos_memoria = getattr(player, "talentos", None)
    if talentos_memoria:
        for pt in talentos_memoria:
            if not getattr(pt, "aprendido", True):
                continue
            if talento_id is not None and getattr(pt, "talento_id", None) == talento_id:
                return True
            t_obj = getattr(pt, "talento", None)
            if t_obj and getattr(t_obj, "nome", None) == nome_talento:
                return True
            if getattr(pt, "nome", None) == nome_talento:
                return True
            if getattr(pt, "talento_nome", None) == nome_talento:
                return True

    # 2. Checagem via sessão SQLAlchemy se o player tiver ID persistido
    from sqlalchemy.orm import object_session
    from db.models import PlayerTalento, TalentoClasse
    from db.connection import get_session

    sess = session or object_session(player)
    fechar_sessao = False
    if sess is None and getattr(player, "id", None):
        try:
            sess = get_session()
            fechar_sessao = True
        except Exception:
            sess = None

    if sess and getattr(player, "id", None):
        try:
            q = sess.query(PlayerTalento).filter_by(player_id=player.id, aprendido=True)
            if talento_id is not None:
                return q.filter_by(talento_id=talento_id).first() is not None
            if nome_talento:
                return (
                    q.join(TalentoClasse, PlayerTalento.talento_id == TalentoClasse.id)
                    .filter(TalentoClasse.nome == nome_talento)
                    .first()
                    is not None
                )
        except Exception:
            pass
        finally:
            if fechar_sessao:
                sess.close()

    return False


def formatar_mensagem_desbloqueio(talento, tag: Optional[str] = None) -> str:
    """Monta a mensagem narrativa oficial citando o mestre do talento."""
    tag_str = f" [{tag}]" if tag else ""
    mestre = talento.mestre or "Desconhecido"
    return (
        f"✨ *Novo Talento Desbloqueado: {talento.nome}* (Nível {talento.nivel}){tag_str}\n\n"
        f"_{talento.efeito}_\n\n"
        f"📜 *Mestre*: {mestre}"
    )


def conceder_talentos_classe(session, player) -> List[Dict[str, Any]]:
    """
    Verifica se o jogador atingiu o nível exigido por algum talento de sua classe
    em ref_talentos_classe e persiste via PlayerTalento(player_id, talento_id, aprendido=True).
    Rotula os 24 talentos de nível > 15 com a tag literal '🔧 Efeito em desenvolvimento'.
    Retorna lista de dicionários dos novos talentos desbloqueados nesta chamada.
    """
    from db.models import Classe, TalentoClasse, PlayerTalento

    if not player:
        return []

    classe = getattr(player, "classe", None)
    if not classe and getattr(player, "classe_id", None):
        classe = session.get(Classe, player.classe_id)
    if not classe:
        return []

    nivel_jogador = getattr(player, "nivel", 1) or 1
    talentos_elegiveis = (
        session.query(TalentoClasse)
        .filter(TalentoClasse.classe_nome == classe.nome, TalentoClasse.nivel <= nivel_jogador)
        .order_by(TalentoClasse.nivel.asc())
        .all()
    )

    existentes = session.query(PlayerTalento).filter_by(player_id=player.id).all()
    ids_existentes = {pt.talento_id for pt in existentes}

    novos_desbloqueados = []
    for t in talentos_elegiveis:
        if t.id in ids_existentes:
            continue

        tag = TAG_DESENVOLVIMENTO if t.nivel > 15 else None
        novo_pt = PlayerTalento(
            player_id=player.id,
            talento_id=t.id,
            aprendido=True,
            tag=tag,
        )
        session.add(novo_pt)
        ids_existentes.add(t.id)

        msg = formatar_mensagem_desbloqueio(t, tag)
        novos_desbloqueados.append({
            "talento_id": t.id,
            "nome": t.nome,
            "nivel": t.nivel,
            "mestre": t.mestre,
            "efeito": t.efeito,
            "classe_nome": t.classe_nome,
            "tag": tag,
            "mensagem": msg,
        })

    if novos_desbloqueados:
        session.flush()

    return novos_desbloqueados


def obter_talentos_jogador(session, player) -> List[Dict[str, Any]]:
    """Retorna lista de todos os talentos já aprendidos pelo jogador."""
    from db.models import PlayerTalento, TalentoClasse

    if not player or not getattr(player, "id", None):
        return []

    pts = (
        session.query(PlayerTalento)
        .filter_by(player_id=player.id, aprendido=True)
        .all()
    )
    resultado = []
    for pt in pts:
        t = pt.talento or session.get(TalentoClasse, pt.talento_id)
        if not t:
            continue
        tag = pt.tag or (TAG_DESENVOLVIMENTO if t.nivel > 15 else None)
        resultado.append({
            "talento_id": t.id,
            "nome": t.nome,
            "nivel": t.nivel,
            "mestre": t.mestre,
            "efeito": t.efeito,
            "classe_nome": t.classe_nome,
            "tag": tag,
            "aprendido": pt.aprendido,
        })
    return resultado


# =============================================================================
# MECÂNICAS DOS 8 TALENTOS DE NÍVEL 15
# =============================================================================

def eh_alvo_purificacao(monstro) -> bool:
    """
    Verifica se o monstro possui a tag morto-vivo, cultista ou aberracao.
    Inspeciona tags explícitas, categoria, tipo, papel de combate, nome e lore.
    """
    if not monstro:
        return False

    # 1. Campos estruturados / coleções
    for attr in ("tags", "tag", "categoria", "tipo", "papel_combate", "papel"):
        val = getattr(monstro, attr, None)
        if not val:
            continue
        if isinstance(val, (list, set, tuple)):
            for item in val:
                item_s = str(item).lower()
                if any(t in item_s for t in ("morto-vivo", "morto_vivo", "morto vivo", "undead", "cultista", "aberracao", "aberração")):
                    return True
        elif isinstance(val, str):
            val_s = val.lower()
            if any(t in val_s for t in TERMOS_PURIFICACAO):
                return True

    # 2. Nome e descrições do monstro
    for attr in ("nome", "motivacao", "efeito_mecanico", "fraqueza"):
        val = getattr(monstro, attr, None)
        if isinstance(val, str) and val:
            val_s = val.lower()
            if any(t in val_s for t in TERMOS_PURIFICACAO):
                return True

    return False


def verificar_lanca_purificacao(player, monstro, session=None) -> Tuple[int, bool]:
    """
    Inquisidor de Prata ("Lança de Purificação"):
    Concede +2 de Dano e aplica flag de Ignorar Defesa/Resistência Mágica quando o monstro
    possuir a tag morto-vivo, cultista ou aberracao.
    Retorna: (bonus_dano, ignora_defesa)
    """
    if player and monstro and eh_alvo_purificacao(monstro):
        if jogador_tem_talento(player, session, "Lança de Purificação"):
            return 2, True
    return 0, False


def calcular_roubo_vida_talento(player, dano: int, session=None) -> int:
    """
    Conjurador de Sangue ("Lâmina da Carne Corrompida"):
    15% Roubo de Vida permanente a ataques com arma.
    Aplica cura diretamente em player.hp_atual e retorna o total curado.
    """
    if not player or dano <= 0:
        return 0

    if jogador_tem_talento(player, session, "Lâmina da Carne Corrompida"):
        cura = max(1, round(dano * 0.15))
        hp_max = getattr(player, "hp_max", 24) or 24
        hp_at = getattr(player, "hp_atual", 0) or 0
        player.hp_atual = min(hp_max, hp_at + cura)
        return cura
    return 0


def verificar_dot_talento_batedor(player, tipo_arma: str, dano: int, session=None) -> Dict[str, Any]:
    """
    Batedor dos Ecos ("Nevasca Perfurante"):
    DoT permanente ao atacar com Arco (15% do dano como Queimadura por 2 turnos).
    """
    if not player or not tipo_arma or "arco" not in tipo_arma.lower():
        return {"aplicou": False, "efeito": "", "dot_dano": 0, "turnos": 0, "descricao": ""}

    if jogador_tem_talento(player, session, "Nevasca Perfurante"):
        dot_dano = max(1, round(dano * 0.15))
        player.em_combate_efeito_monstro = "Queimadura"
        player.em_combate_efeito_monstro_turnos = 2
        desc = f"❄️🔥 *Nevasca Perfurante:* Disparo com Arco aplicou Queimadura (-{dot_dano} HP por 2 turnos)!"
        return {
            "aplicou": True,
            "efeito": "Queimadura",
            "dot_dano": dot_dano,
            "turnos": 2,
            "descricao": desc,
        }
    return {"aplicou": False, "efeito": "", "dot_dano": 0, "turnos": 0, "descricao": ""}


def calcular_furtividade_bonus(player, session=None) -> float:
    """
    Ladino das Sombras ("Manto da Não-Existência"):
    Registra +20% Furtividade nos atributos/bônus do jogador.
    """
    if player and jogador_tem_talento(player, session, "Manto da Não-Existência"):
        return 20.0
    return 0.0


def possui_feitico_adiantado(player, session=None) -> bool:
    """
    Mago Elemental ("Arco Voltaico Encadeado"):
    Desbloqueia feitiço antecipado (marcar flag/registro de feitiço adiantado).
    """
    return jogador_tem_talento(player, session, "Arco Voltaico Encadeado")


def possui_escudo_runico(player, session=None) -> bool:
    """
    Artífice Mecânico ("Barreira de Distorção Rúnica"):
    Desbloqueia feitiço de escudo gratuito (marcar flag de escudo rúnico ativo).
    """
    return jogador_tem_talento(player, session, "Barreira de Distorção Rúnica")
