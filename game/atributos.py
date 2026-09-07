"""
Cálculos de atributos reais de personagens (HP, Vigor, Mana, Defesa, Crítico e Equipamentos).
Zero dependência de atributos legados (FOR/DES/CON/INT/SAB/CAR).
"""

def calcular_hp_maximo(player=None, session=None, nivel=None, classe=None) -> int:
    """
    Calcula o HP Máximo a partir da Curva Mestra no banco de dados e do hp_mult da classe:
    HP_Max = round(hp_curva * hp_mult)
    Não possui nenhuma influência de CON.
    """
    from db.models import CurvaMestra, Classe
    from db.connection import get_session
    from sqlalchemy.orm import object_session

    sess = session or (object_session(player) if player else None)
    fechar_sessao = False
    if sess is None:
        sess = get_session()
        fechar_sessao = True

    try:
        nv = nivel if nivel is not None else (player.nivel if player else 1)
        curva = sess.query(CurvaMestra).filter_by(nivel=nv).first()
        hp_curva = curva.hp if curva and curva.hp is not None else round(20 + 2.6 * nv)

        cls = classe
        if cls is None and player:
            cls = getattr(player, "classe", None)
            if cls is None and getattr(player, "classe_id", None):
                cls = sess.get(Classe, player.classe_id)

        hp_mult = cls.hp_mult if (cls and cls.hp_mult is not None) else 1.0
        hp_final = int(round(hp_curva * hp_mult))
        if player and getattr(player, "debuff_ativo", None) == "Ferida Profunda":
            hp_final = max(1, int(round(hp_final * 0.90)))
        return hp_final
    finally:
        if fechar_sessao:
            sess.close()


def calcular_vigor_maximo(player=None, classe=None) -> int:
    """
    Retorna o vigor máximo da classe (80, 70 ou 60).
    Aplica penalidades cumulativas e independentes:
    - Debuff 'Fadiga Persistente': -10 Vigor
    - Mutação 'Pulmões de Cinza Morta': -10 Vigor
    """
    cls = classe
    if cls is None and player:
        cls = getattr(player, "classe", None)
        if cls is None and getattr(player, "classe_id", None):
            from db.models import Classe
            from db.connection import get_session
            from sqlalchemy.orm import object_session
            sess = object_session(player)
            fechar = False
            if sess is None:
                sess = get_session()
                fechar = True
            try:
                cls = sess.get(Classe, player.classe_id)
            finally:
                if fechar:
                    sess.close()
    vig = int(cls.vigor_inicial) if (cls and cls.vigor_inicial is not None) else 60
    if player:
        if getattr(player, "debuff_ativo", None) == "Fadiga Persistente":
            vig -= 10
        try:
            from db.models import PlayerMutacao
            from sqlalchemy.orm import object_session
            sess = object_session(player)
            if sess and getattr(player, "id", None):
                mutacoes = sess.query(PlayerMutacao).filter_by(player_id=player.id).all()
            else:
                mutacoes = getattr(player, "mutacoes", [])
            if mutacoes and any(getattr(m, "mutacao_id", 0) == 9 or "Pulmões de Cinza" in (getattr(m, "nome", "") or "") for m in mutacoes):
                vig -= 10
        except Exception:
            pass
    return max(10, vig)


def calcular_mana_maximo(player=None, session=None, nivel=None, classe=None) -> int:
    """
    Mana_Max = round(mana_curva(nivel) * classe.mana_mult).
    Não possui nenhuma influência de INT.
    """
    from db.models import CurvaMestra, Classe
    from db.connection import get_session
    from sqlalchemy.orm import object_session

    sess = session or (object_session(player) if player else None)
    fechar_sessao = False
    if sess is None:
        sess = get_session()
        fechar_sessao = True
    try:
        nv = nivel if nivel is not None else (player.nivel if player else 1)
        curva = sess.query(CurvaMestra).filter_by(nivel=nv).first()
        mana_curva = curva.mana if curva and curva.mana is not None else round(17 + 1.5 * nv)

        cls = classe
        if cls is None and player:
            cls = getattr(player, "classe", None)
            if cls is None and getattr(player, "classe_id", None):
                cls = sess.get(Classe, player.classe_id)

        mana_mult = cls.mana_mult if (cls and cls.mana_mult is not None) else 1.0
        mana_base = int(round(mana_curva * mana_mult))
        if player:
            try:
                from db.models import PlayerMutacao
                if sess and getattr(player, "id", None):
                    mutacoes = sess.query(PlayerMutacao).filter_by(player_id=player.id).all()
                else:
                    mutacoes = getattr(player, "mutacoes", [])
                if mutacoes and any(getattr(m, "mutacao_id", 0) == 14 or "Marca Estelar" in (getattr(m, "nome", "") or "") for m in mutacoes):
                    mana_base += 15
            except Exception:
                pass
        return mana_base
    finally:
        if fechar_sessao:
            sess.close()


calcular_hp_max = calcular_hp_maximo
calcular_vigor_max = calcular_vigor_maximo
calcular_mana_max = calcular_mana_maximo


def calcular_critico_chance(player=None, classe=None, bonus_itens_pct=0, bonus_passivas_pct=0, nivel_proficiencia=0) -> float:
    """
    Retorna a porcentagem total de chance de crítico baseada na classe e bônus:
    Crit_Chance = crit_base_classe + bonus_itens_pct + bonus_passivas_pct + proficiencia + titulos
    Não possui nenhuma influência de DES.
    """
    cls = classe
    if cls is None and player:
        cls = getattr(player, "classe", None)
        if cls is None and getattr(player, "classe_id", None):
            from db.models import Classe
            from db.connection import get_session
            from sqlalchemy.orm import object_session
            sess = object_session(player)
            fechar = False
            if sess is None:
                sess = get_session()
                fechar = True
            try:
                cls = sess.get(Classe, player.classe_id)
            finally:
                if fechar:
                    sess.close()
    crit_base = cls.crit_base if (cls and cls.crit_base is not None) else 0.0

    bonus_prof = (min(30, max(0, nivel_proficiencia or 0)) // 5) * 0.5

    bonus_titulo = 0.0
    if player:
        t_ativo = getattr(player, "titulo_ativo", None)
        if t_ativo == "Veterano de Mil Batalhas":
            bonus_titulo = 1.0
        elif t_ativo == "Açougueiro":
            bonus_titulo = 2.0

    return float(crit_base + bonus_itens_pct + bonus_passivas_pct + bonus_prof + bonus_titulo)


def calcular_defesa_total(player, session=None) -> int:
    """
    Fórmula oficial V1.0 (Regras e Fórmulas R15):
    Defesa Total = soma dos 8 slots equipados + Defesa_Nativa_Classe (0, 1 ou 2)
    + Bônus de Corrupção Estágio (bonus_defesa: 0, -1, -2, -3, -4)
    + Bônus de Mutações ativas (Couraça +3, Ossos +2, Tentáculo -1, Verme -1, Olho Adicional -1)
    Garante piso final de Defesa >= 0 (max(0, defesa_total)).
    """
    from db.models import PlayerInventario, Armadura, PlayerMutacao, Classe
    from db.connection import get_session
    from sqlalchemy.orm import object_session
    from game.corrupcao import bonus_defesa_corrupcao

    sess = session or object_session(player)
    fechar_sessao = False
    if sess is None:
        sess = get_session()
        fechar_sessao = True

    try:
        defesa_pecas = 0
        equipados = (
            sess.query(PlayerInventario)
            .filter_by(player_id=player.id, equipado=True)
            .all()
        )
        for inv in equipados:
            if inv.tipo_item == "armadura" and inv.item_ref_id:
                arm = sess.query(Armadura).filter_by(id=inv.item_ref_id).first()
                if arm and arm.defesa_comum:
                    def_val = arm.defesa_comum
                    if getattr(inv, "danificado", False):
                        def_val = round(def_val * 0.5)
                    defesa_pecas += def_val

        # Defesa nativa da classe (substitui modificador de DES)
        def_nativa = 0
        cls = getattr(player, "classe", None)
        if cls is None and getattr(player, "classe_id", None):
            cls = sess.get(Classe, player.classe_id)
        if cls and cls.def_nativa is not None:
            def_nativa = cls.def_nativa

        bonus_corr = bonus_defesa_corrupcao(player)

        bonus_mutacoes = 0
        mutacoes = sess.query(PlayerMutacao).filter_by(player_id=player.id).all()
        for mut in mutacoes:
            mid = mut.mutacao_id
            mnome = mut.nome or ""
            if mid == 3 or "Couraça Escamosa" in mnome:
                bonus_mutacoes += 3
            elif mid == 11 or "Ossos de Pedra" in mnome:
                bonus_mutacoes += 2
            elif mid == 7 or "Membro Mimetizado" in mnome:
                bonus_mutacoes -= 1
            elif mid == 15 or "Sensibilidade de Verme" in mnome:
                bonus_mutacoes -= 1
            elif mid == 17 or "Olho Adicional" in mnome:
                bonus_mutacoes -= 1

        # --- Lote 3: Guerreiro da Forja ("Muralha Inabalável") ---
        # Concede +3 de Defesa quando player.hp_atual < (player.hp_max * 0.30)
        bonus_talento_defesa = 0
        hp_at = getattr(player, "hp_atual", None)
        hp_mx = getattr(player, "hp_max", None)
        if hp_at is not None and hp_mx and hp_at < (hp_mx * 0.30):
            from game.talentos import jogador_tem_talento
            if jogador_tem_talento(player, sess, "Muralha Inabalável"):
                bonus_talento_defesa = 3

        defesa_total = defesa_pecas + def_nativa + bonus_corr + bonus_mutacoes + bonus_talento_defesa
        return max(0, defesa_total)
    finally:
        if fechar_sessao:
            sess.close()


def calcular_furtividade(player, session=None) -> float:
    """
    Calcula o bônus percentual de Furtividade do jogador.
    Ladino das Sombras ("Manto da Não-Existência"): +20% (+20.0).
    """
    from game.talentos import calcular_furtividade_bonus
    return calcular_furtividade_bonus(player, session)


def resolver_item_do_kit(session, parte: str):
    """
    Resolve um item do kit inicial de uma classe (da tabela ref_armas ou ref_armaduras de Tier 1)
    a partir de uma string de descrição (ex: '2x Adaga de Sucata Enferrujada', 'Escudo de Sucata').
    Aplica normalização de acentos (_norm), correspondência exata por variação e fallback parcial por tipo/slot.
    Retorna um dicionário estruturado com os dados reais do item ou None.
    """
    from db.models import Arma, Armadura
    import unicodedata

    def _norm(texto):
        if not texto:
            return ""
        return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower().strip()

    if not parte:
        return None

    qty = 1
    item_str = parte.strip()
    if item_str.startswith("2x "):
        qty = 2
        item_str = item_str[3:].strip()
    elif item_str.startswith("1x "):
        item_str = item_str[3:].strip()

    n_str = _norm(item_str)
    match_item = None
    tipo_item = None
    slot_armadura = None

    armas_t1 = session.query(Arma).filter(Arma.tier == "Sucata Enferrujada").all()
    armaduras_t1 = session.query(Armadura).filter(Armadura.tier == "Sucata Enferrujada").all()

    # 1. Correspondência exata por variacao
    for a in armas_t1:
        if _norm(a.variacao) == n_str:
            match_item = a
            tipo_item = "arma"
            break
    if not match_item:
        for arm in armaduras_t1:
            if _norm(arm.variacao) == n_str:
                match_item = arm
                tipo_item = "armadura"
                slot_armadura = arm.slot
                break

    # 2. Fallback: correspondência parcial
    if not match_item:
        for a in armas_t1:
            if _norm(a.tipo) in n_str or n_str in _norm(a.variacao):
                match_item = a
                tipo_item = "arma"
                break
    if not match_item:
        for arm in armaduras_t1:
            if _norm(arm.slot) in n_str or n_str in _norm(arm.variacao):
                match_item = arm
                tipo_item = "armadura"
                slot_armadura = arm.slot
                break

    if not match_item:
        return None

    tipo_ou_slot = match_item.tipo if tipo_item == "arma" else match_item.slot
    valor_stat = match_item.dano_comum if tipo_item == "arma" else match_item.defesa_comum
    tipo_stat = "Dano" if tipo_item == "arma" else "Defesa"

    return {
        "item": match_item,
        "tipo_item": tipo_item,
        "slot": slot_armadura,
        "tipo_ou_slot": tipo_ou_slot,
        "qty": qty,
        "nome": match_item.variacao,
        "valor_stat": valor_stat or 0,
        "tipo_stat": tipo_stat,
    }


def calcular_defesa_preview_classe(session, classe, itens_kit_resolvidos=None) -> int:
    """
    Função dedicada e isolada para cálculo de Defesa na prévia da classe (Nível 1).
    Soma 'classe.def_nativa' com a 'defesa_comum' das peças de armadura/escudo do kit inicial
    que seriam equipadas no nível 1 (no máximo 1 peça por slot, reproduzindo a regra de entregar_kit_inicial).
    Garante risco zero de regressão em combate ativo, mantendo calcular_defesa_total intocada.
    """
    if not classe:
        return 0

    def_total = classe.def_nativa or 0
    if itens_kit_resolvidos is None:
        if not classe.kit_inicial:
            return def_total
        partes = [p.strip() for p in classe.kit_inicial.split("+")]
        itens_kit_resolvidos = [resolver_item_do_kit(session, p) for p in partes]

    slots_vistos = set()
    for res in itens_kit_resolvidos:
        if res and res["tipo_item"] == "armadura":
            slot = res["slot"]
            if slot and slot not in slots_vistos:
                slots_vistos.add(slot)
                def_total += (res["valor_stat"] or 0)

    return max(0, def_total)


def entregar_kit_inicial(session, player, classe):
    """
    Entrega e equipa automaticamente o kit inicial previsto pela classe do jogador.
    Garante idempotência: se o jogador já tiver itens em seu inventário, não duplica.
    Equipa a 1ª arma e 1 peça por slot de armadura (Peitoral, Escudo, Elmo).
    Peças sobressalentes (ex: 2ª adaga do Ladino) ficam na mochila com equipado=False.
    """
    from db.models import PlayerInventario

    # Idempotência: se já possui itens no inventário, não recria
    ja_tem = session.query(PlayerInventario).filter_by(player_id=player.id).first()
    if ja_tem:
        return

    if not classe or not classe.kit_inicial:
        return

    partes = [p.strip() for p in classe.kit_inicial.split("+")]
    slots_equipados = set()
    arma_equipada = False

    for parte in partes:
        res = resolver_item_do_kit(session, parte)
        if not res:
            continue

        match_item = res["item"]
        tipo_item = res["tipo_item"]
        slot_armadura = res["slot"]
        qty = res["qty"]
        nome_item = res["nome"]

        for i in range(qty):
            deve_equipar = False
            if tipo_item == "arma" and not arma_equipada:
                deve_equipar = True
                arma_equipada = True
            elif tipo_item == "armadura" and slot_armadura and slot_armadura not in slots_equipados:
                deve_equipar = True
                slots_equipados.add(slot_armadura)

            novo_item = PlayerInventario(
                player_id=player.id,
                tipo_item=tipo_item,
                item_ref_id=match_item.id,
                nome_item=nome_item,
                quantidade=1,
                equipado=deve_equipar,
                danificado=False,
            )
            session.add(novo_item)

    session.commit()


def deletar_player_cascata(session, telegram_id: str) -> bool:
    """
    Deleta com segurança e em cascata todos os dados de um jogador no banco de dados:
    - player_inventario
    - player_proficiencias
    - player_reputacao_faccao
    - player_quests
    - player_receitas
    - player_mutacoes
    - player_talentos
    - player_knowledge
    - player_titulos
    - players (registro principal)
    Retorna True se o jogador existia e foi deletado, ou False caso não existisse.
    """
    from db.models import (
        Player, PlayerInventario, PlayerProficiencia, PlayerReputacaoFaccao,
        PlayerQuest, PlayerReceita, PlayerMutacao, PlayerTalento,
        PlayerKnowledge, PlayerTitulo,
    )
    player = session.query(Player).filter_by(telegram_id=str(telegram_id)).first()
    if not player:
        return False
    pid = player.id
    session.query(PlayerInventario).filter_by(player_id=pid).delete()
    session.query(PlayerProficiencia).filter_by(player_id=pid).delete()
    session.query(PlayerReputacaoFaccao).filter_by(player_id=pid).delete()
    session.query(PlayerQuest).filter_by(player_id=pid).delete()
    session.query(PlayerReceita).filter_by(player_id=pid).delete()
    session.query(PlayerMutacao).filter_by(player_id=pid).delete()
    session.query(PlayerTalento).filter_by(player_id=pid).delete()
    session.query(PlayerKnowledge).filter_by(player_id=pid).delete()
    session.query(PlayerTitulo).filter_by(player_id=pid).delete()
    session.delete(player)
    session.commit()
    return True



