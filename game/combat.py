"""
Combate — usa a fórmula original do jogo: d20 + BônusAtaque >= Defesa do alvo.
Natural 1 sempre erra. Natural 20 sempre acerta e causa dano em dobro (crítico).
"""
import random
import re
import math
from dataclasses import dataclass


@dataclass
class ResultadoAtaque:
    acertou: bool
    critico: bool
    dano: int
    rolagem: int


@dataclass
class ResultadoHabilidade:
    sucesso: bool
    motivo_falha: str = ""
    mensagem: str = ""
    habilidade_nome: str = ""
    tipo_acao: str = ""
    recurso_tipo: str = ""
    recurso_gasto: int = 0
    hp_sacrificado: int = 0
    dano: int = 0
    cura: int = 0
    critico: bool = False
    acertou: bool = False
    rolagem_d20: int = 0
    efeito_tipo: str = ""
    efeito_valor: float = 0.0
    efeito_descricao: str = ""


def resolver_ataque(
    atq_bonus: int,
    defesa_alvo: int,
    dano_base: int,
    bonus_critico_pct: float = 0.0,
    mult_critico: float = None,
    nivel_proficiencia: int = 0
) -> ResultadoAtaque:
    """
    Combate d20 com Bounded Accuracy e Faixa de Ameaça (Decisão de Design 1):
    - 1 Natural: falha automática.
    - 20 Natural: acerto crítico automático incondicional.
    - Faixa de Crítico = max(1, round(bonus_critico_pct / 5))
    - Margem de Ameaça = 21 - Faixa de Crítico
    - Multiplicador de Crítico Dinâmico: 2.0x base + 0.05x a cada 4 níveis de proficiência (máx 2.35x no Nv 28-30).
    - d20 >= Margem E d20 + atq_bonus >= defesa_alvo: Acerto Crítico (dano x mult_critico).
    - d20 + atq_bonus < defesa_alvo: Erro (golpe não atinge a defesa do alvo).
    - d20 + atq_bonus >= defesa_alvo: Acerto Normal.
    """
    if mult_critico is None:
        mult_critico = 2.0 + (min(30, max(0, nivel_proficiencia or 0)) // 4) * 0.05
    elif mult_critico == 2.0 and nivel_proficiencia > 0:
        mult_critico = 2.0 + (min(30, max(0, nivel_proficiencia)) // 4) * 0.05

    d20 = random.randint(1, 20)

    if d20 == 1:
        return ResultadoAtaque(acertou=False, critico=False, dano=0, rolagem=d20)

    if d20 == 20:
        return ResultadoAtaque(acertou=True, critico=True, dano=max(1, round(dano_base * mult_critico)), rolagem=d20)

    faixa_critico = max(1, round((bonus_critico_pct or 0.0) / 5))
    margem_ameaca = 21 - faixa_critico

    atingiu_defesa = (d20 + atq_bonus) >= defesa_alvo
    if not atingiu_defesa:
        return ResultadoAtaque(acertou=False, critico=False, dano=0, rolagem=d20)

    critico = (d20 >= margem_ameaca)
    dano = max(1, round(dano_base * mult_critico)) if critico else dano_base
    return ResultadoAtaque(acertou=True, critico=critico, dano=dano, rolagem=d20)


def calcular_dano_fisico(
    dano_arma: int,
    mult_habilidade: float = 1.0,
    mult_empunhadura: float = 1.0,
    mult_corrupcao: float = 1.0,
    player=None,
    tipo_arma: str = None,
    monstro=None,
    session=None,
) -> int:
    """
    Cálculo de Dano Físico oficial V1.0:
    Dano = Dano_Arma * Multiplicador_Habilidade * Multiplicador_Empunhadura * Multiplicador_Corrupção.
    Aplica modificador de mutação 2 (-1 Dano com Adaga, Arco, Cetro) e título 'Mestre de Uma Só Arma' (+5% Dano).
    Lote 3:
    - Bárbaro ("Golpe Desesperado"): +2 Dano quando HP < 30%.
    - Inquisidor ("Lança de Purificação"): +2 Dano vs mortos-vivos, cultistas e aberrações.
    Zero dependência de atributo FOR.
    """
    dano = dano_arma
    mult_extra = 1.0

    if player:
        try:
            mutacoes = getattr(player, "mutacoes", None)
            if mutacoes and tipo_arma in ("Adaga", "Arco", "Cetro"):
                if any(getattr(m, "mutacao_id", 0) == 2 or "Garras de Quitina" in (getattr(m, "nome", "") or "") for m in mutacoes):
                    dano = max(1, dano - 1)
        except Exception:
            pass

        if getattr(player, "titulo_ativo", None) == "Mestre de Uma Só Arma":
            mult_extra += 0.05

        # --- Lote 3: Bárbaro da Fenda ("Golpe Desesperado") ---
        # Concede +2 de Dano quando player.hp_atual < (player.hp_max * 0.30)
        hp_at = getattr(player, "hp_atual", None)
        hp_mx = getattr(player, "hp_max", None)
        if hp_at is not None and hp_mx and hp_at < (hp_mx * 0.30):
            from game.talentos import jogador_tem_talento
            if jogador_tem_talento(player, session, "Golpe Desesperado"):
                dano += 2

        # --- Lote 3: Inquisidor de Prata ("Lança de Purificação") ---
        # Concede +2 de Dano quando o monstro possuir a tag morto-vivo, cultista ou aberracao
        if monstro:
            from game.talentos import verificar_lanca_purificacao
            bonus_dano_purif, _ = verificar_lanca_purificacao(player, monstro, session)
            dano += bonus_dano_purif

    return max(1, round(dano * mult_habilidade * mult_empunhadura * mult_corrupcao * mult_extra))


def calcular_dano_magico(dano_base_magia: int, mult_magia: float = 1.0, mult_elemental: float = 1.0, mult_corrupcao: float = 1.0) -> int:
    """
    Cálculo de Dano Mágico oficial V1.0:
    Dano = Dano_Base_Magia * Multiplicador_Magia * Multiplicador_Elemental * Multiplicador_Corrupção.
    Zero dependência de atributo INT.
    """
    return max(1, round(dano_base_magia * mult_magia * mult_elemental * mult_corrupcao))


def calcular_custo_vigor(classe_nome: str, custo_base: int, em_combate_turnos: int = 0) -> int:
    """
    Aplica a desvantagem do Inquisidor de Prata:
    +1 VIG extra na primeira ação ofensiva do combate (em_combate_turnos == 0).
    """
    if classe_nome == "Inquisidor de Prata" and em_combate_turnos == 0:
        return custo_base + 1
    return custo_base





def executar_habilidade_ativa(
    classe_nome: str,
    jogador,
    alvo,
    nivel_habilidade: int = 1,
    session=None,
    dano_arma_equipada: int = None,
    d20_override: int = None,
) -> ResultadoHabilidade:
    """
    Dispatcher central de Habilidades Ativas Iniciais V1.0:
    - Lê dados da tabela ref_habilidades_ativas via SQLAlchemy.
    - Valida e debita custo de recurso (Vigor ou Mana).
    - Conjurador de Sangue: ativa Pacto Escarlate (1 HP por 3 Mana) se faltar Mana.
    - Calcula dano base:
      * Física: round(dano_arma_equipada * dano_pct_rankN)
      * Mágica: round(Dano_Arma_Padrao(nível) * dano_pct_rankN)
    - Aplica modificadores temporários de dano (Fúria).
    - Batedor (Tiro Perfurante): reduz Defesa do alvo apenas neste ataque (-1 a -3 pts).
    - Rola ataque d20 com bounded accuracy e margem de crítico.
    - Aplica efeitos secundários (Atordoamento, Proteção Radiante, Cura, Execução <30% HP, Queimadura DoT, Fúria, Sangramento DoT).
    """
    from db.connection import get_session
    from db.models import HabilidadeAtiva, CurvaMestra
    from game.atributos import calcular_critico_chance

    close_session = False
    if session is None:
        session = get_session()
        close_session = True

    try:
        hab = None
        if hasattr(jogador, "classe_id") and jogador.classe_id:
            hab = session.query(HabilidadeAtiva).filter_by(classe_id=jogador.classe_id).first()
        if not hab and classe_nome:
            primeira_palavra = classe_nome.split()[0]
            hab = session.query(HabilidadeAtiva).filter(HabilidadeAtiva.classe_nome.ilike(f"%{primeira_palavra}%")).first()

        if not hab:
            return ResultadoHabilidade(sucesso=False, motivo_falha="Habilidade ativa não encontrada para a classe.")

        rank = max(1, min(5, nivel_habilidade or getattr(jogador, "habilidade_ativa_nivel", 1) or 1))

        dano_pct_map = {
            1: hab.dano_pct_rank1,
            2: hab.dano_pct_rank2,
            3: hab.dano_pct_rank3,
            4: hab.dano_pct_rank4,
            5: hab.dano_pct_rank5,
        }
        ef_val_map = {
            1: hab.efeito_secundario_rank1,
            2: hab.efeito_secundario_rank2,
            3: hab.efeito_secundario_rank3,
            4: hab.efeito_secundario_rank4,
            5: hab.efeito_secundario_rank5,
        }

        mult_dano = dano_pct_map.get(rank, hab.dano_pct_rank1)
        ef_val = ef_val_map.get(rank, hab.efeito_secundario_rank1)

        recurso_tipo = hab.recurso_tipo
        custo_base = hab.custo_recurso
        custo_final = custo_base
        hp_sacrificado = 0

        if recurso_tipo == "Vigor":
            custo_final = calcular_custo_vigor(hab.classe_nome, custo_base, getattr(jogador, "em_combate_turnos", 0))
            vig_atual = getattr(jogador, "vig_atual", 0) or 0
            if vig_atual < custo_final:
                return ResultadoHabilidade(
                    sucesso=False,
                    motivo_falha=f"⚡ Vigor insuficiente ({vig_atual}/{custo_final} VIG necessários).",
                    habilidade_nome=hab.habilidade_nome,
                    tipo_acao=hab.tipo_acao,
                    recurso_tipo="Vigor",
                    recurso_gasto=0,
                )
            jogador.vig_atual = vig_atual - custo_final

        elif recurso_tipo == "Mana":
            mana_atual = getattr(jogador, "mana_atual", 0) or 0
            if mana_atual >= custo_base:
                jogador.mana_atual = mana_atual - custo_base
            else:
                nome_c = hab.classe_nome.lower()
                if "conjurador" in nome_c or "hemomante" in nome_c:
                    mana_faltante = custo_base - mana_atual
                    custo_hp = math.ceil(mana_faltante / 3)
                    hp_atual = getattr(jogador, "hp_atual", 0) or 0
                    if hp_atual <= custo_hp:
                        return ResultadoHabilidade(
                            sucesso=False,
                            motivo_falha=f"🩸 Vida e Mana insuficientes para o Pacto Escarlate (precisa de {custo_hp} HP).",
                            habilidade_nome=hab.habilidade_nome,
                            tipo_acao=hab.tipo_acao,
                            recurso_tipo="Mana",
                            recurso_gasto=0,
                        )
                    jogador.mana_atual = 0
                    jogador.hp_atual = hp_atual - custo_hp
                    hp_sacrificado = custo_hp
                else:
                    return ResultadoHabilidade(
                        sucesso=False,
                        motivo_falha=f"🔷 Mana insuficiente ({mana_atual}/{custo_base} Mana necessária).",
                        habilidade_nome=hab.habilidade_nome,
                        tipo_acao=hab.tipo_acao,
                        recurso_tipo="Mana",
                        recurso_gasto=0,
                    )

        # Cálculo de Dano Base
        nivel_jogador = getattr(jogador, "nivel", 1) or 1
        curva = session.query(CurvaMestra).filter_by(nivel=nivel_jogador).first()
        dano_arma_padrao = curva.dano_arma_padrao if curva else 3

        if hab.tipo_acao == "Física":
            arma_val = dano_arma_equipada if (dano_arma_equipada is not None and dano_arma_equipada > 0) else dano_arma_padrao
            dano_calculado = max(1, round(arma_val * mult_dano))
        else:
            dano_calculado = max(1, round(dano_arma_padrao * mult_dano))

        # Modificador de Fúria temporária (+% dano)
        if getattr(jogador, "em_combate_efeito_jogador", None) == "Fúria":
            dano_calculado = max(1, round(dano_calculado * 1.25))

        # Redução de Defesa do Tiro Perfurante no d20 deste ataque
        defesa_alvo = getattr(alvo, "defesa", 11) or 11
        if hab.efeito_secundario_tipo == "perfuracao_defesa_pts":
            defesa_alvo = max(1, defesa_alvo - int(ef_val))

        atq_bonus = curva.atq_bonus if curva else 2
        crit_pct = calcular_critico_chance(jogador)

        if d20_override is not None:
            d20 = d20_override
            faixa = max(1, round(crit_pct / 5))
            margem = 21 - faixa
            if d20 == 1:
                acertou, critico = False, False
            elif d20 == 20:
                acertou, critico = True, True
            elif d20 >= margem and (d20 + atq_bonus) >= defesa_alvo:
                acertou, critico = True, True
            elif (d20 + atq_bonus) < defesa_alvo:
                acertou, critico = False, False
            else:
                acertou, critico = True, False
            dano_final = (dano_calculado * 2) if critico else (dano_calculado if acertou else 0)
            res = ResultadoAtaque(acertou=acertou, critico=critico, dano=dano_final, rolagem=d20)
        else:
            res = resolver_ataque(atq_bonus, defesa_alvo, dano_calculado, bonus_critico_pct=crit_pct)

        cura = 0
        efeito_desc = ""
        dano_final = res.dano

        if res.acertou:
            # Apunhalada nas Sombras (Ladino): execução se HP alvo <= 30%
            if hab.efeito_secundario_tipo == "execucao_hp_baixo_pct":
                hp_atual_m = getattr(jogador, "em_combate_hp_monstro", None)
                if hp_atual_m is None:
                    hp_atual_m = getattr(alvo, "hp_atual", getattr(alvo, "hp", 100))
                hp_max_m = getattr(alvo, "hp", 100) or 100
                if hp_max_m > 0 and (hp_atual_m / hp_max_m) <= 0.30:
                    bonus_exec = 1.0 + (ef_val / 100.0)
                    dano_final = max(1, round(dano_final * bonus_exec))
                    efeito_desc = f"🗡️ *Execução!* (+{int(ef_val)}% de dano em alvo ferido)"

            # Conjurador de Sangue: Drenagem Vital (100% cura)
            elif hab.efeito_secundario_tipo == "cura_pct_dano":
                cura = dano_final
                hp_max = getattr(jogador, "hp_max", 24) or 24
                hp_atual = getattr(jogador, "hp_atual", 0) or 0
                jogador.hp_atual = min(hp_max, hp_atual + cura)
                efeito_desc = f"🩸 *Drenagem Vital:* Converteu {cura} de dano em Vida recuperada!"

            # Guerreiro da Forja: Atordoamento
            elif hab.efeito_secundario_tipo == "atordoamento_chance_pct":
                chance = ef_val / 100.0
                if (d20_override is not None and d20_override >= 10) or random.random() < chance:
                    jogador.em_combate_efeito_monstro = "Atordoado"
                    jogador.em_combate_efeito_monstro_turnos = 1
                    efeito_desc = "🔨 *Impacto Esmagador:* O inimigo foi atordoado por 1 turno!"

            # Inquisidor de Prata: Proteção Radiante
            elif hab.efeito_secundario_tipo == "reducao_dano_recebido_pct":
                jogador.em_combate_efeito_jogador = "Proteção Radiante"
                jogador.em_combate_efeito_jogador_turnos = 2
                efeito_desc = f"✨ *Proteção Radiante:* Dano recebido reduzido em {int(ef_val)}% por 2 turnos!"

            # Mago Elemental: Queimadura DoT
            elif hab.efeito_secundario_tipo == "queimadura_dot_pct":
                jogador.em_combate_efeito_monstro = "Queimadura"
                jogador.em_combate_efeito_monstro_turnos = 2
                efeito_desc = f"🔥 *Chamas Residuais:* Inimigo infligido com Queimadura por 2 turnos!"

            # Bárbaro da Fenda: Fúria
            elif hab.efeito_secundario_tipo == "furia_dano_causado_pct":
                jogador.em_combate_efeito_jogador = "Fúria"
                jogador.em_combate_efeito_jogador_turnos = 2
                efeito_desc = f"💢 *Fúria Desenfreada:* Bônus de +{int(ef_val)}% de dano causado por 2 turnos!"

            # Artífice Mecânico: Sangramento DoT
            elif hab.efeito_secundario_tipo == "sangramento_dot_pct":
                jogador.em_combate_efeito_monstro = "Sangramento"
                jogador.em_combate_efeito_monstro_turnos = 2
                efeito_desc = f"⚙️ *Estilhaços Lacerantes:* Inimigo lacerado com Sangramento por 2 turnos!"

            # Batedor dos Ecos: Perfuração
            elif hab.efeito_secundario_tipo == "perfuracao_defesa_pts":
                efeito_desc = f"🎯 *Tiro Perfurante:* Reduziu {int(ef_val)} pts de Defesa do alvo neste ataque!"

        return ResultadoHabilidade(
            sucesso=True,
            habilidade_nome=hab.habilidade_nome,
            tipo_acao=hab.tipo_acao,
            recurso_tipo=recurso_tipo,
            recurso_gasto=custo_final,
            hp_sacrificado=hp_sacrificado,
            dano=dano_final,
            cura=cura,
            critico=res.critico,
            acertou=res.acertou,
            rolagem_d20=res.rolagem,
            efeito_tipo=hab.efeito_secundario_tipo,
            efeito_valor=ef_val,
            efeito_descricao=efeito_desc,
        )
    finally:
        if close_session:
            session.close()



def aplicar_efeito_status(jogador, alvo, efeito_nome: str, efeito_valor: float, dano_causado: int = 0) -> str:
    """
    Engine unificada de DoT/CC para Habilidades Ativas e Golpes de Armas.
    Retorna o texto descritivo para os logs de combate.
    """
    if not efeito_nome:
        return ""
    ef_norm = efeito_nome.lower()
    desc = ""

    if "sangramento" in ef_norm:
        jogador.em_combate_efeito_monstro = "Sangramento"
        jogador.em_combate_efeito_monstro_turnos = 2
        dot = max(1, round(dano_causado * (efeito_valor / 100.0 if efeito_valor > 1 else 0.15)))
        desc = f"🩸 *Sangramento aplicado!* (-{dot} HP por 2 turnos)"

    elif "queimadura" in ef_norm:
        jogador.em_combate_efeito_monstro = "Queimadura"
        jogador.em_combate_efeito_monstro_turnos = 2
        dot = max(1, round(dano_causado * (efeito_valor / 100.0 if efeito_valor > 1 else 0.15)))
        desc = f"🔥 *Queimadura aplicada!* (-{dot} HP por 2 turnos)"

    elif "atordoamento" in ef_norm or "atordoado" in ef_norm:
        jogador.em_combate_efeito_monstro = "Atordoado"
        jogador.em_combate_efeito_monstro_turnos = 1
        desc = "🔨 *Impacto Esmagador:* O inimigo foi atordoado por 1 turno!"

    elif "rouba vida" in ef_norm or "cura" in ef_norm:
        pct = (efeito_valor / 100.0) if efeito_valor > 1 else (efeito_valor or 0.15)
        cura = max(1, round(dano_causado * pct))
        hp_max = getattr(jogador, "hp_max", 24) or 24
        jogador.hp_atual = min(hp_max, (getattr(jogador, "hp_atual", 0) or 0) + cura)
        desc = f"🩸 *Rouba Vida:* Converteu {cura} de dano em Vida recuperada!"

    elif "fragilidade" in ef_norm:
        jogador.em_combate_efeito_monstro = "Fragilidade"
        jogador.em_combate_efeito_monstro_turnos = 2
        pts = int(efeito_valor) if efeito_valor else 2
        desc = f"🛡️ *Fragilidade aplicada!* Defesa do alvo reduzida em {pts} por 2 turnos!"

    elif "proteção radiante" in ef_norm or "protecao radiante" in ef_norm:
        jogador.em_combate_efeito_jogador = "Proteção Radiante"
        jogador.em_combate_efeito_jogador_turnos = 2
        desc = f"✨ *Proteção Radiante:* Dano recebido reduzido em {int(efeito_valor)}% por 2 turnos!"

    elif "fúria" in ef_norm or "furia" in ef_norm:
        jogador.em_combate_efeito_jogador = "Fúria"
        jogador.em_combate_efeito_jogador_turnos = 2
        desc = f"💢 *Fúria Desenfreada:* Bônus de +{int(efeito_valor)}% de dano causado por 2 turnos!"

    return desc


def rolar_efeito_arma(arma, jogador, alvo, dano_causado: int) -> str:
    """
    Rola a chance de disparar o efeito especial da arma equipada em um hit bem-sucedido.
    """
    if not arma or not getattr(arma, "efeito_especial", None) or not getattr(arma, "efeito_chance_pct", 0):
        return ""
    chance = arma.efeito_chance_pct / 100.0
    if random.random() < chance:
        return aplicar_efeito_status(
            jogador, alvo, arma.efeito_especial, arma.efeito_valor or 0.0, dano_causado
        )
    return ""


def chance_fuga(player=None, vig_atual: int = None, vig_max: int = None, bonus: int = None) -> bool:
    """
    Nova regra Vigor-based:
    - Tentar fugir custa 10 de Vigor (deduzido de vig_atual sempre, sucesso ou não).
    - Chance = 0.40 + (vig_atual / vig_max) * 0.20 (teto 60%, piso 40%).
    - Modificadores: Debuff 'Marca do Medo' (-5%), Mutações (-10% / -5%), Título 'Sobrevivente Nato' (+5%).
    - Sucesso contabiliza em player.fugas_com_sucesso_qtd.
    """
    if player is not None:
        v_at = getattr(player, "vig_atual", 0)
        if v_at is None:
            v_at = 0
        v_mx = getattr(player, "vig_max", 60) or 60
        player.vig_atual = max(0, v_at - 10)
    else:
        v_at = vig_atual if vig_atual is not None else 60
        v_mx = vig_max if vig_max is not None else 60

    ratio = max(0.0, min(1.0, v_at / max(1, v_mx)))
    chance = 0.40 + (ratio * 0.20)
    chance = max(0.40, min(0.60, chance))

    if player is not None:
        if getattr(player, "debuff_ativo", None) == "Marca do Medo":
            chance -= 0.05
        try:
            mutacoes = getattr(player, "mutacoes", None)
            if mutacoes:
                for m in mutacoes:
                    mid = getattr(m, "mutacao_id", 0)
                    if mid in (3, 6):  # Couraça Escamosa (-10%), Voz Dupla (-10%)
                        chance -= 0.10
                    elif mid == 16:  # Seiva da Árvore Sangrenta (-5%)
                        chance -= 0.05
        except Exception:
            pass
        if getattr(player, "titulo_ativo", None) == "Sobrevivente Nato":
            chance += 0.05

    chance = max(0.05, min(0.95, chance))
    sucesso = random.random() < chance
    if sucesso and player is not None and hasattr(player, "fugas_com_sucesso_qtd"):
        player.fugas_com_sucesso_qtd = (player.fugas_com_sucesso_qtd or 0) + 1
    return sucesso


def calcular_modificador_empunhadura(tipo_arma: str, slot_secundario_ocupado: bool) -> tuple[float, str]:
    """
    Regra da aba Armas da planilha:
    - Espada: Versátil (+20% com 2 mãos se secundário livre)
    - Machado: Versátil (+25% com 2 mãos se secundário livre)
    - Maça: Versátil (+20% com 2 mãos se secundário livre)
    - Arco: Sempre 2 mãos (bônus base já ajustado)
    - Adaga / Manopla / Cetro: 1 mão
    Retorna (multiplicador, descricao_empunhadura).
    """
    if not tipo_arma:
        return 1.0, "Uma Mão"

    tipo_norm = tipo_arma.lower().replace("ç", "c")
    if not slot_secundario_ocupado:
        if "machado" in tipo_norm:
            return 1.25, "Duas Mãos (+25%)"
        elif "espada" in tipo_norm or "maca" in tipo_norm:
            return 1.20, "Duas Mãos (+20%)"

    return 1.0, "Uma Mão"


from game.corrupcao import PONTOS_CORRUPCAO_POR_PAPEL

FRASE_DERROTA_POR_TIPO = {
    "Estrada Perigosa": "Viajantes encontraram seu corpo estirado na poeira e o arrastaram até os portões da cidade. Seus bolsos foram revirados pelo caminho.",
    "Campo de Batalha": "Viajantes encontraram seu corpo estirado na poeira e o arrastaram até os portões da cidade. Seus bolsos foram revirados pelo caminho.",
    "Floresta Perigosa": "O sangue negro da fera atingiu suas feridas abertas. Caçadores o resgataram antes que a podridão tomasse conta do restante do seu corpo.",
    "Pantano": "O sangue negro da fera atingiu suas feridas abertas. Caçadores o resgataram antes que a podridão tomasse conta do restante do seu corpo.",
    "Mina": "Mineiros retiraram seus ossos quebrados do fundo das galerias escuras. O ar tóxico e a poeira de pedra ainda queimam em seus pulmões.",
    "Caverna": "Mineiros retiraram seus ossos quebrados do fundo das galerias escuras. O ar tóxico e a poeira de pedra ainda queimam em seus pulmões.",
    "Dungeon": "O eco dos corredores de pedra foi a última coisa que você ouviu antes de apagar. Saqueadores o deixaram nos degraus da cidade em troca de algumas moedas.",
    "Ruina": "O eco dos corredores de pedra foi a última coisa que você ouviu antes de apagar. Saqueadores o deixaram nos degraus da cidade em troca de algumas moedas.",
    "Covil de Boss": "A presença esmagadora do monstro partiu seu espírito. A marca carmesim arde sob sua carne como fogo vivo enquanto você acorda febril na estalagem.",
    "Fenda": "A presença esmagadora do monstro partiu seu espírito. A marca carmesim arde sob sua carne como fogo vivo enquanto você acorda febril na estalagem.",
}
FRASE_DERROTA_PADRAO = "Alguém o encontrou desacordado e o trouxe de volta à cidade, mais vivo do que deveria."


def frase_derrota_por_tipo_local(tipo_local):
    return FRASE_DERROTA_POR_TIPO.get(tipo_local, FRASE_DERROTA_PADRAO)


TABELA_DEBUFFS_PESOS = [
    ("Ferida Profunda", 12),
    ("Tremor nos Braços", 8),
    ("Fadiga Persistente", 8),
    ("Marca do Medo", 4),
    (None, 68),
]


def sortear_debuff_derrota(player=None) -> str | None:
    """
    Sorteia um debuff de derrota da tabela ponderada oficial.
    Regra: se o jogador já possui um debuff ativo, NÃO sorteia novo debuff (não acumula).
    Aplica imunidades concedidas por mutações ('Coração Silencioso' e 'Sensibilidade de Verme').
    """
    if player and getattr(player, "debuff_ativo", None):
        return None  # Mantém a ferida atual até ser curada

    opcoes = []
    for nome, peso in TABELA_DEBUFFS_PESOS:
        opcoes.extend([nome] * peso)
    sorteado = random.choice(opcoes)
    if not sorteado:
        return None

    if player:
        try:
            mutacoes = getattr(player, "mutacoes", None)
            if mutacoes:
                nomes_mut = {getattr(m, "nome", "") for m in mutacoes}
                ids_mut = {getattr(m, "mutacao_id", 0) for m in mutacoes}
                if sorteado == "Marca do Medo" and (4 in ids_mut or any("Coração Silencioso" in nm for nm in nomes_mut)):
                    return None
                if sorteado == "Fadiga Persistente" and (15 in ids_mut or any("Sensibilidade de Verme" in nm for nm in nomes_mut)):
                    return None
        except Exception:
            pass

    return sorteado


def resolver_derrota(player_ouro, player_corrupcao, player_hora_do_mundo, monstro_papel, tipo_local_atual, player=None):
    """Calcula as consequencias puras da derrota (sem tocar em Telegram/sessao),
    pra poder testar isolado e reaproveitar. Retorna um dict pronto pra aplicar no Player."""
    pontos_infeccao = PONTOS_CORRUPCAO_POR_PAPEL.get(monstro_papel, 2)
    ouro_perdido = int((player_ouro or 0) * 0.10)

    if player:
        try:
            mutacoes = getattr(player, "mutacoes", None)
            if mutacoes:
                # Mutação 13: Asas Atrofiadas de Morcego (-50% perda de ouro)
                if any(getattr(m, "mutacao_id", 0) == 13 or "Asas Atrofiadas" in (getattr(m, "nome", "") or "") for m in mutacoes):
                    ouro_perdido = int(round(ouro_perdido * 0.5))
                # Mutações 14 e 20 (+1 e +2 corrupção extra)
                for m in mutacoes:
                    mid = getattr(m, "mutacao_id", 0)
                    if mid == 14:
                        pontos_infeccao += 1
                    elif mid == 20:
                        pontos_infeccao += 2
        except Exception:
            pass

    debuff_sorteado = sortear_debuff_derrota(player)
    return {
        "pontos_infeccao": pontos_infeccao,
        "corrupcao_nova": min(100, (player_corrupcao or 0) + pontos_infeccao),
        "ouro_perdido": ouro_perdido,
        "ouro_novo": (player_ouro or 0) - ouro_perdido,
        "hora_nova": ((player_hora_do_mundo or 0) + 4) % 24,
        "frase_narrativa": frase_derrota_por_tipo_local(tipo_local_atual),
        "debuff_sorteado": debuff_sorteado,
    }


def verificar_pode_poupar(monstro, hp_atual_monstro, hp_max_monstro):
    """
    Retorna True se o jogador pode poupar esse monstro agora, baseado em:
    - Papel de Combate = Nao-hostil (pode poupar desde o inicio)
    - Interacao Ambiental menciona 'rende-se a X% de HP' e ja chegou nesse ponto
    """
    if not monstro.papel_combate:
        return False
    papel = monstro.papel_combate.lower().replace("ã", "a")
    if "nao-hostil" in papel or "nao hostil" in papel:
        return True

    texto = (monstro.interacao_ambiental or "")
    m = re.search(r"(\d+)%\s*(de\s*)?hp", texto, re.IGNORECASE)
    if m and hp_max_monstro:
        limite_pct = int(m.group(1))
        hp_pct_atual = (hp_atual_monstro / hp_max_monstro) * 100
        return hp_pct_atual <= limite_pct
    return False


# =========================================================================
# HOOKS MECÂNICOS DE MUTAÇÕES EM COMBATE (Item 10 do Prompt Mestre Final)
# =========================================================================

def _obter_mutacoes_player(player):
    """Busca mutações do player de forma segura no banco ou na instância."""
    if not player:
        return []
    try:
        from db.models import PlayerMutacao
        from sqlalchemy.orm import object_session
        sess = object_session(player)
        if sess and getattr(player, "id", None):
            return sess.query(PlayerMutacao).filter_by(player_id=player.id).all()
    except Exception:
        pass
    return getattr(player, "mutacoes", []) or []


def aplicar_contra_ataque_mutacao(player) -> int:
    """Mutação 5 (Sangue Cáustico Ácido): espirra ácido causando 4 de dano ao sofrer hit corpo a corpo."""
    mutacoes = _obter_mutacoes_player(player)
    if mutacoes and any(getattr(m, "mutacao_id", 0) == 5 or "Sangue Cáustico" in (getattr(m, "nome", "") or "") for m in mutacoes):
        return 4
    return 0


def dano_passivo_turno_mutacao(player) -> int:
    """Mutação 12 (Presença Gélida do Ceifador): 2 de dano passivo de frio por turno aos inimigos."""
    mutacoes = _obter_mutacoes_player(player)
    if mutacoes and any(getattr(m, "mutacao_id", 0) == 12 or "Presença Gélida" in (getattr(m, "nome", "") or "") for m in mutacoes):
        return 2
    return 0


def dano_primeiro_hit_mutacao(player, turno: int = 1) -> int:
    """Mutação 8 (Mandíbula de Fera): mordida brutal no primeiro turno causa 6 de dano fixo."""
    if not player or turno > 1:
        return 0
    mutacoes = _obter_mutacoes_player(player)
    if mutacoes and any(getattr(m, "mutacao_id", 0) == 8 or "Mandíbula de Fera" in (getattr(m, "nome", "") or "") for m in mutacoes):
        return 6
    return 0


def resistencia_dot_mutacao(player, tipo_dot: str) -> float:
    """
    Retorna porcentagem de redução de dano contra DoT específico:
    - Mutação 9 (Pulmões de Cinza Morta): +15% resist Queimadura
    - Mutação 16 (Seiva da Árvore Sangrenta): +10% resist Sangramento
    """
    if not player or not tipo_dot:
        return 0.0
    resist = 0.0
    mutacoes = _obter_mutacoes_player(player)
    for m in mutacoes:
        mid = getattr(m, "mutacao_id", 0)
        mnome = getattr(m, "nome", "") or ""
        if (mid == 9 or "Pulmões de Cinza" in mnome) and "queimadura" in tipo_dot.lower():
            resist += 0.15
        elif (mid == 16 or "Seiva da Árvore" in mnome) and "sangramento" in tipo_dot.lower():
            resist += 0.10
    return min(0.75, resist)


def acao_extra_disponivel_mutacao(player) -> bool:
    """Mutação 20 (Centelha do Aspecto Desperto): concede 1 ação extra por combate."""
    mutacoes = _obter_mutacoes_player(player)
    if mutacoes and any(getattr(m, "mutacao_id", 0) == 20 or "Centelha do Aspecto" in (getattr(m, "nome", "") or "") for m in mutacoes):
        return True
    return False


def bonus_ataque_mutacao(player, tipo_arma: str = None, hora_do_mundo: int = 12) -> int:
    """
    Retorna modificador de bônus de ataque conferido por mutações ativas:
    - Mutação 1 (Olhos de Vidro Negro): +2 à noite (18h-5h), -1 de dia (6h-17h)
    - Mutação 7 (Membro Mimetizado / Tentáculo): +1 Atq flat
    - Mutação 12 (Presença Gélida): -1 Atq flat
    - Mutação 17 (Olho Adicional na Palma da Mão): +2 Atq com Arco e Cetro
    """
    mutacoes = _obter_mutacoes_player(player)
    if not mutacoes:
        return 0
    atq_mod = 0
    is_noite = (hora_do_mundo >= 18 or hora_do_mundo < 6)
    for m in mutacoes:
        mid = getattr(m, "mutacao_id", 0)
        mnome = getattr(m, "nome", "") or ""
        if mid == 1 or "Olhos de Vidro" in mnome:
            atq_mod += (2 if is_noite else -1)
        elif mid == 7 or "Membro Mimetizado" in mnome:
            atq_mod += 1
        elif mid == 12 or "Presença Gélida" in mnome:
            atq_mod -= 1
        elif mid == 17 or "Olho Adicional" in mnome:
            if tipo_arma in ("Arco", "Cetro"):
                atq_mod += 2
    return atq_mod
