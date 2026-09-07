"""
Sistema de Corrupção e Sanidade — A Infecção que Segura o Mundo.
Alinhado rigorosamente aos Itens 9 e 10 do Prompt Mestre Final.
"""
import random
from datetime import datetime
from db.models import PlayerMutacao

PONTOS_CORRUPCAO_POR_PAPEL = {
    "Comum": 2, "comum": 2,
    "Elite": 3, "elite": 3,
    "Boss": 5, "boss": 5,
    "Cosmico": 5, "cosmico": 5,
}

# =========================================================================
# 7 ESTÁGIOS DA INFECÇÃO (Item 9 do Prompt Mestre Final)
# =========================================================================
ESTAGIOS = {
    0: {
        "estagio": "Estágio 0",
        "faixa": "0 a 19 Pontos",
        "nome": "Puro",
        "sintomas": "Nenhuma alteração visível; mente sã e controle total do corpo.",
        "bonus": "Nenhum bônus adicional.",
        "penalidade": "Nenhuma penalidade.",
        "mod_cura": 1.0,
        "bonus_defesa": 0,
        "mult_dano": 1.0,
        "bloqueia_cura": False,
        "bloqueia_purificacao": False,
        "descricao": "Puro — sem efeito.",
    },
    1: {
        "estagio": "Estágio I",
        "faixa": "20 a 39 Pontos",
        "nome": "Manchado",
        "sintomas": "Veias avermelhadas visíveis nos pulsos.",
        "bonus": "+5% de Dano em ataques físicos e mágicos.",
        "penalidade": "-1 na Defesa física.",
        "mod_cura": 1.0,
        "bonus_defesa": -1,
        "mult_dano": 1.05,
        "bloqueia_cura": False,
        "bloqueia_purificacao": False,
        "descricao": "Manchado — +5% dano, -1 Defesa.",
    },
    2: {
        "estagio": "Estágio II",
        "faixa": "40 a 59 Pontos",
        "nome": "Corrompido",
        "sintomas": "Pele cinzenta rígida; pupilas não dilatam mais.",
        "bonus": "+10% de Dano em ataques físicos e mágicos.",
        "penalidade": "-2 na Defesa física; -15% na cura recebida.",
        "mod_cura": 0.85,
        "bonus_defesa": -2,
        "mult_dano": 1.10,
        "bloqueia_cura": False,
        "bloqueia_purificacao": False,
        "descricao": "Corrompido — +10% dano, -2 Defesa, -15% cura.",
    },
    3: {
        "estagio": "Estágio III",
        "faixa": "60 a 79 Pontos",
        "nome": "Possuído",
        "sintomas": "Unhas endurecidas como garras; sussurros contínuos na mente.",
        "bonus": "+18% de Dano em ataques físicos e mágicos.",
        "penalidade": "-3 na Defesa física; -30% na cura recebida.",
        "mod_cura": 0.70,
        "bonus_defesa": -3,
        "mult_dano": 1.18,
        "bloqueia_cura": False,
        "bloqueia_purificacao": False,
        "descricao": "Possuído — +18% dano, -3 Defesa, -30% cura. Ao entrar: +1 mutação extra garantida.",
    },
    4: {
        "estagio": "Estágio IV",
        "faixa": "80 a 94 Pontos",
        "nome": "Hospedeiro",
        "sintomas": "Tentáculos de carne sob a pele; olhos verticais múltiplos.",
        "bonus": "+25% de Dano em ataques físicos e mágicos.",
        "penalidade": "-4 na Defesa física; -50% na cura recebida; preços em lojas de cidade +20%.",
        "mod_cura": 0.50,
        "bonus_defesa": -4,
        "mult_dano": 1.25,
        "bloqueia_cura": False,
        "bloqueia_purificacao": False,
        "descricao": "Hospedeiro — +25% dano, -4 Defesa, -50% cura, preços em lojas de cidade +20%.",
    },
    5: {
        "estagio": "Estágio V",
        "faixa": "95 a 99 Pontos",
        "nome": "Ponto de Não Retorno",
        "sintomas": "Você sente que está perdendo o controle...",
        "bonus": "+25% de Dano em ataques físicos e mágicos.",
        "penalidade": "-4 na Defesa física; -50% na cura recebida; preços em lojas de cidade +20%.",
        "mod_cura": 0.50,
        "bonus_defesa": -4,
        "mult_dano": 1.25,
        "bloqueia_cura": False,
        "bloqueia_purificacao": False,
        "descricao": "Ponto de Não Retorno — mesmos números do estágio 4, aviso narrativo a cada exploração.",
    },
    6: {
        "estagio": "Estágio VI",
        "faixa": "100 Pontos",
        "nome": "Assimilação",
        "sintomas": "O corpo se funde completamente à vontade da Mão; o herói perde sua consciência humana.",
        "bonus": "Transforma-se em um Chefe de Elite a serviço do Culto do Aspecto.",
        "penalidade": "O personagem é retirado do controle do jogador tornando-se inimigo da campanha.",
        "mod_cura": 0.0,
        "bonus_defesa": -4,
        "mult_dano": 1.25,
        "bloqueia_cura": True,
        "bloqueia_purificacao": True,
        "descricao": "Assimilação — personagem sai do controle do jogador, vira inimigo da campanha.",
    },
}

# =========================================================================
# 20 MUTAÇÕES MECÂNICAS DA CARNE (Item 10 do Prompt Mestre Final)
# =========================================================================
TABELA_MUTACOES_1D20 = {
    1: {
        "id": 1,
        "nome": "Olhos de Vidro Negro",
        "categoria": "Óptica",
        "deformacao": "As pupilas cobrem toda a esclera em preto lustroso.",
        "bonus_mecanico": "Ataques noturnos recebem +2 de Bônus de Ataque.",
        "penalidade": "Sensibilidade à luz do dia (-1 em ataques diurnos).",
        "bonus_tipo": "atq_noturno",
        "bonus_valor": 2.0,
        "penalidade_tipo": "atq_diurno",
        "penalidade_valor": -1.0,
        "lore": '"O olhar que enxerga através das fendas dimensionais."',
    },
    2: {
        "id": 2,
        "nome": "Garras de Quitina Retorcida",
        "categoria": "Membros",
        "deformacao": "As unhas das mãos se fundem em lâminas curvas escuras de quitina.",
        "bonus_mecanico": "Ataques desarmados causam Sangramento (15% dano contínuo).",
        "penalidade": "Incompatibilidade anatômica com armas leves (-1 Dano com Adaga, Arco e Cetro).",
        "bonus_tipo": "sangramento_desarmado",
        "bonus_valor": 15.0,
        "penalidade_tipo": "dano_arma_tipo",
        "penalidade_valor": -1.0,
        "armas_penalizadas": ["Adaga", "Arco", "Cetro"],
        "lore": '"A carne que rejeita a ferramenta e se torna arma."',
    },
    3: {
        "id": 3,
        "nome": "Couraça Escamosa de Ébano",
        "categoria": "Pele",
        "deformacao": "Placas pretas e rígidas brotam sobre o tórax e costas.",
        "bonus_mecanico": "+3 de Defesa física permanente.",
        "penalidade": "Rigidez motora excessiva (-10% de Chance de Fuga).",
        "bonus_tipo": "defesa_flat",
        "bonus_valor": 3.0,
        "penalidade_tipo": "chance_fuga_pct",
        "penalidade_valor": -10.0,
        "lore": '"Escamas que repelem o aço comum mas pesam na alma."',
    },
    4: {
        "id": 4,
        "nome": "Coração Silencioso",
        "categoria": "Interno",
        "deformacao": "O pulso cessa completamente; o sangue corre em fluxo frio contínuo.",
        "bonus_mecanico": "Imunidade total ao debuff 'Marca do Medo'.",
        "penalidade": "Circulação amortecida (-20% de cura recebida de poções e descanso).",
        "bonus_tipo": "imune_debuff",
        "bonus_valor": "Marca do Medo",
        "penalidade_tipo": "cura_recebida_pct",
        "penalidade_valor": -20.0,
        "lore": '"Um coração que não bate não pode temer."',
    },
    5: {
        "id": 5,
        "nome": "Sangue Cáustico Ácido",
        "categoria": "Fluido",
        "deformacao": "O sangue ganha tom esverdeado fosforescente e fumega ao ar livre.",
        "bonus_mecanico": "Ao sofrer dano corpo a corpo, espirra ácido causando 4 de dano fixo no atacante.",
        "penalidade": "Acidez estomacal corrosiva (20% de chance de poções falharem ao serem ingeridas).",
        "bonus_tipo": "contra_ataque_dano",
        "bonus_valor": 4.0,
        "penalidade_tipo": "chance_pocao_falha_pct",
        "penalidade_valor": 20.0,
        "lore": '"Cada gota derramada cobra seu pedágio da carne do inimigo."',
    },
    6: {
        "id": 6,
        "nome": "Voz Dupla dos Ecos",
        "categoria": "Garganta",
        "deformacao": "Uma segunda corda vocal ressoa sob o queixo em tom polifônico.",
        "bonus_mecanico": "Persuasão hipnótica em mercadores (5% de desconto geral em lojas).",
        "penalidade": "Hesitação ao recuar (-10% de Chance de Fuga).",
        "bonus_tipo": "desconto_loja_pct",
        "bonus_valor": 5.0,
        "penalidade_tipo": "chance_fuga_pct",
        "penalidade_valor": -10.0,
        "lore": '"A voz que negocia com as sombras."',
    },
    7: {
        "id": 7,
        "nome": "Membro Mimetizado (Tentáculo)",
        "categoria": "Membros",
        "deformacao": "Um tentáculo flexível de carne muscular escura emerge abaixo da omoplata.",
        "bonus_mecanico": "+1 no Bônus de Ataque físico.",
        "penalidade": "Distorção postural desequilibrada (-1 na Defesa física).",
        "bonus_tipo": "atq_flat",
        "bonus_valor": 1.0,
        "penalidade_tipo": "defesa_flat",
        "penalidade_valor": -1.0,
        "lore": '"Um terceiro braço que não conhece a dor."',
    },
    8: {
        "id": 8,
        "nome": "Mandíbula de Fera",
        "categoria": "Face",
        "deformacao": "A mandíbula se alarga com fileiras duplas de dentes serrilhados.",
        "bonus_mecanico": "Mordida brutal no primeiro turno do combate causa 6 de dano fixo extra.",
        "penalidade": "Aparência aterrorizante (+5% no preço de compra com mercadores de cidades).",
        "bonus_tipo": "dano_fixo_1x_combate",
        "bonus_valor": 6.0,
        "penalidade_tipo": "preco_compra_pct",
        "penalidade_valor": 5.0,
        "lore": '"A fome que nunca é saciada por palavras."',
    },
    9: {
        "id": 9,
        "nome": "Pulmões de Cinza Morta",
        "categoria": "Interno",
        "deformacao": "Os pulmões se petrificam em tecido poroso esponjoso acinzentado.",
        "bonus_mecanico": "+15% de resistência ao dano contínuo de Queimadura.",
        "penalidade": "Capacidade aeróbica reduzida (-10 de Vigor Máximo).",
        "bonus_tipo": "resist_dot_pct",
        "bonus_valor": 15.0,
        "penalidade_tipo": "vigor_maximo_flat",
        "penalidade_valor": -10.0,
        "dot_tipo": "Queimadura",
        "lore": '"Respira cinzas e sopra brasas mortas."',
    },
    10: {
        "id": 10,
        "nome": "Mente Fragmentada dos Cem Reis",
        "categoria": "Mente",
        "deformacao": "Sussurros de dezenas de consciências antigas sobrepõem os pensamentos.",
        "bonus_mecanico": "+10% de XP ganho em combate por assimilação acelerada.",
        "penalidade": "Desestabilização psíquica ao sofrer acerto crítico (-10% de dano causado).",
        "bonus_tipo": "xp_ganho_pct",
        "bonus_valor": 10.0,
        "penalidade_tipo": "dano_apos_sofrer_critico_pct",
        "penalidade_valor": -10.0,
        "lore": '"Cem reis mortos falando ao mesmo tempo na mesma cabeça."',
    },
    11: {
        "id": 11,
        "nome": "Ossos de Pedra Fóssil",
        "categoria": "Esqueleto",
        "deformacao": "O esqueleto se calcifica com minerais negros ultradensos.",
        "bonus_mecanico": "+2 de Defesa física permanente.",
        "penalidade": "Peso corporal aumentado (+15% de custo de Vigor em exploração).",
        "bonus_tipo": "defesa_flat",
        "bonus_valor": 2.0,
        "penalidade_tipo": "custo_vigor_exploracao_pct",
        "penalidade_valor": 15.0,
        "lore": '"A estrutura de um monumento fúnebre dentro da carne."',
    },
    12: {
        "id": 12,
        "nome": "Presença Gélida do Ceifador",
        "categoria": "Aura",
        "deformacao": "O ar num raio de dois passos congela em geada constante ao redor do herói.",
        "bonus_mecanico": "Inimigos em combate sofrem 2 de dano passivo de frio por turno.",
        "penalidade": "Membros entorpecidos pelo frio constante (-1 no Bônus de Ataque físico).",
        "bonus_tipo": "dano_passivo_por_turno",
        "bonus_valor": 2.0,
        "penalidade_tipo": "atq_flat",
        "penalidade_valor": -1.0,
        "lore": '"O inverno da Mão que caminha onde o herói pisa."',
    },
    13: {
        "id": 13,
        "nome": "Asas Atrofiadas de Morcego",
        "categoria": "Membros",
        "deformacao": "Membranas coriáceas escuras emergem sob as axilas e costelas.",
        "bonus_mecanico": "Queda amortecida em derrotas (reduz a perda de ouro em 50%).",
        "penalidade": "Anatomia aberrante inviabiliza armaduras comuns (+50% de custo ao comprar armaduras).",
        "bonus_tipo": "reducao_perda_ouro_derrota_pct",
        "bonus_valor": 50.0,
        "penalidade_tipo": "preco_armadura_pct",
        "penalidade_valor": 50.0,
        "lore": '"Asas que não voam, mas amortecem a queda."',
    },
    14: {
        "id": 14,
        "nome": "Marca Estelar Pulsante",
        "categoria": "Pele",
        "deformacao": "Um símbolo geométrico pulsa luz violácea viva sobre o peito.",
        "bonus_mecanico": "+15 de Mana Máxima permanente.",
        "penalidade": "Afinidade magnética com a Infecção (+1 de Corrupção extra sofrida em derrotas).",
        "bonus_tipo": "mana_maxima_flat",
        "bonus_valor": 15.0,
        "penalidade_tipo": "corrupcao_ganho_extra",
        "penalidade_valor": 1.0,
        "lore": '"O farol que guia o olhar dos deuses corrompidos."',
    },
    15: {
        "id": 15,
        "nome": "Sensibilidade de Verme das Profundezas",
        "categoria": "Sentidos",
        "deformacao": "A pele perde pigmento e desenvolve microporos que sentem vibrações no solo.",
        "bonus_mecanico": "Imunidade total ao debuff 'Fadiga Persistente'.",
        "penalidade": "Pele delgada e hipersensível (-1 na Defesa física).",
        "bonus_tipo": "imune_debuff",
        "bonus_valor": "Fadiga Persistente",
        "penalidade_tipo": "defesa_flat",
        "penalidade_valor": -1.0,
        "lore": '"Sentir cada tremor da terra antes que ele aconteça."',
    },
    16: {
        "id": 16,
        "nome": "Seiva da Árvore Sangrenta",
        "categoria": "Fluido",
        "deformacao": "O sangue coagula instantaneamente em resina espessa aromática.",
        "bonus_mecanico": "+10% de resistência ao dano contínuo de Sangramento.",
        "penalidade": "Articulações endurecidas pela resina (-5% de Chance de Fuga).",
        "bonus_tipo": "resist_dot_pct",
        "bonus_valor": 10.0,
        "penalidade_tipo": "chance_fuga_pct",
        "penalidade_valor": -5.0,
        "dot_tipo": "Sangramento",
        "lore": '"A seiva que fecha o ferimento antes da dor passar."',
    },
    17: {
        "id": 17,
        "nome": "Olho Adicional na Palma da Mão",
        "categoria": "Óptica",
        "deformacao": "Um olho funcional de íris amarela abre-se no centro da palma da mão hábil.",
        "bonus_mecanico": "Pontaria sobrenatural (+2 no Bônus de Ataque com Arco e Cetro).",
        "penalidade": "Vulnerabilidade ao empunhar escudos (-1 na Defesa física).",
        "bonus_tipo": "atq_arma_tipo",
        "bonus_valor": 2.0,
        "penalidade_tipo": "defesa_flat",
        "penalidade_valor": -1.0,
        "armas_bonificadas": ["Arco", "Cetro"],
        "lore": '"A mira que não depende do rosto."',
    },
    18: {
        "id": 18,
        "nome": "Digestão de Minérios",
        "categoria": "Digestivo",
        "deformacao": "O estômago desenvolve moenda de placas de basalto mineral.",
        "bonus_mecanico": "Capacidade de consumir 1 material comum de forja para restaurar 10 HP.",
        "penalidade": "Trato digestivo petrificado (comidas comuns e rações perdem efeito).",
        "bonus_tipo": "consumir_material_cura",
        "bonus_valor": 10.0,
        "penalidade_tipo": "comida_sem_efeito",
        "penalidade_valor": 1.0,
        "lore": '"Triturar pedras como se fossem pão quente."',
    },
    19: {
        "id": 19,
        "nome": "Aura de Decomposição Acelerada",
        "categoria": "Aura",
        "deformacao": "Plantas pequenas murcham e insetos morrem ao toque do herói.",
        "bonus_mecanico": "Corrosão de espólios extrai ouro extra (+5% de ouro ganho em combate).",
        "penalidade": "Deterioração celular constante (-15% de cura recebida de poções e descanso).",
        "bonus_tipo": "ouro_ganho_pct",
        "bonus_valor": 5.0,
        "penalidade_tipo": "cura_recebida_pct",
        "penalidade_valor": -15.0,
        "lore": '"A podridão que caminha à frente de cada passo."',
    },
    20: {
        "id": 20,
        "nome": "Centelha do Aspecto Desperto",
        "categoria": "Mítica",
        "deformacao": "Um fragmento de energia estelar puro brilha pulsando dentro do peito.",
        "bonus_mecanico": "Concede 1 ação extra por combate sem custo de vida.",
        "penalidade": "Conexão aberta com a Mão (+2 de Corrupção extra sofrida em derrotas).",
        "bonus_tipo": "acao_extra_1x_combate",
        "bonus_valor": 1.0,
        "penalidade_tipo": "corrupcao_ganho_extra",
        "penalidade_valor": 2.0,
        "lore": '"A prova viva de que a Mão já escolheu seu próximo general."',
    },
}

TABELA_MUTACOES = TABELA_MUTACOES_1D20


def estagio_corrupcao(pontos: int) -> int:
    """Calcula o estágio de infecção de 0 a 6 com base na pontuação de corrupção."""
    p = max(0, min(100, pontos or 0))
    if p < 20:
        return 0
    elif p < 40:
        return 1
    elif p < 60:
        return 2
    elif p < 80:
        return 3
    elif p < 95:
        return 4
    elif p < 100:
        return 5
    return 6


obter_estagio_corrupcao = estagio_corrupcao


def info_estagio(pontos: int) -> dict:
    return ESTAGIOS[estagio_corrupcao(pontos)]


def modificador_cura_corrupcao(player) -> float:
    """
    Retorna o modificador de cura recebida (poções, descanso, curandeiro):
    Combina estágio de corrupção (Estágio 2: 0.85, Estágio 3: 0.70, Estágio 4/5: 0.50, Estágio 6: 0.0)
    com penalidades de mutações ativas (Coração Silencioso -20%, Aura de Decomposição -15%).
    """
    corr = getattr(player, "corrupcao", 0) or 0
    est = estagio_corrupcao(corr)
    mod = ESTAGIOS[est]["mod_cura"]

    try:
        from db.models import PlayerMutacao
        from sqlalchemy.orm import object_session
        sess = object_session(player)
        if sess and getattr(player, "id", None):
            mutacoes = sess.query(PlayerMutacao).filter_by(player_id=player.id).all()
        else:
            mutacoes = getattr(player, "mutacoes", []) or []
        if mutacoes:
            for m in mutacoes:
                mid = getattr(m, "mutacao_id", 0)
                if mid == 4:  # Coração Silencioso (-20%)
                    mod -= 0.20
                elif mid == 19:  # Aura de Decomposição (-15%)
                    mod -= 0.15
    except Exception:
        pass

    return max(0.0, mod)


def bonus_defesa_corrupcao(player) -> int:
    """Retorna a penalidade/bônus de defesa física do estágio de corrupção (0, -1, -2, -3, -4)."""
    corr = getattr(player, "corrupcao", 0) or 0
    est = estagio_corrupcao(corr)
    return ESTAGIOS[est]["bonus_defesa"]


def modificador_dano_corrupcao(player) -> float:
    """Retorna o multiplicador de dano concedido pela corrupção (+5% a +25%)."""
    corr = getattr(player, "corrupcao", 0) or 0
    est = estagio_corrupcao(corr)
    return ESTAGIOS[est]["mult_dano"]


def custo_purificacao(corrupcao_atual: int) -> int:
    """
    Preço em ouro pra reduzir 20 pontos de Corrupção, escalando com o estágio atual:
    round(50 * (1.5 ** estagio_atual)) com arredondamento padrão half-up (ex: 112.5 -> 113).
    """
    p = max(0, corrupcao_atual or 0)
    est = estagio_corrupcao(p)
    return int(50 * (1.5 ** est) + 0.5)


def purificar_corrupcao(session, player, pontos: int = 20) -> tuple[bool, str, int]:
    """
    Reduz até `pontos` de corrupção do jogador debitando o custo em ouro.
    Retorna (sucesso, mensagem, ouro_gasto).
    """
    corr_atual = player.corrupcao or 0
    if corr_atual <= 0:
        return False, "Sua carne e espírito já estão completamente puros.", 0

    custo = custo_purificacao(corr_atual)
    if (player.ouro or 0) < custo:
        return False, f"Ouro insuficiente para o ritual de Purificação. Custo: {custo} 💰 (Você possui {player.ouro or 0} 💰).", 0

    player.ouro = (player.ouro or 0) - custo
    nova_corr = max(0, corr_atual - pontos)
    player.corrupcao = nova_corr
    session.commit()
    return True, f"Purificação realizada! Corrupção reduzida de {corr_atual} para {nova_corr}. (-{custo} 💰)", custo


def sortear_mutacao(session, player) -> PlayerMutacao:
    """Rola 1d20 para obter uma mutação da carne. Evita duplicatas se possível."""
    mutacoes_atuais = {m.mutacao_id for m in session.query(PlayerMutacao).filter_by(player_id=player.id).all()}
    disponiveis = [i for i in range(1, 21) if i not in mutacoes_atuais]
    rolagem = random.choice(disponiveis) if disponiveis else random.randint(1, 20)

    dados = TABELA_MUTACOES_1D20[rolagem]
    nova_mutacao = PlayerMutacao(
        player_id=player.id,
        mutacao_id=rolagem,
        nome=dados["nome"],
        categoria=dados["categoria"],
        deformacao=dados["deformacao"],
        bonus_mecanico=dados["bonus_mecanico"],
        penalidade=dados["penalidade"],
        lore=dados["lore"],
        data_aquisicao=datetime.utcnow(),
    )
    session.add(nova_mutacao)
    session.commit()
    return nova_mutacao


def aplicar_ganho_corrupcao(session, player, monstro_papel: str) -> tuple[int, int, bool]:
    """
    Aplica o ganho escalonado de corrupção pós-derrota (+2 comum, +3 elite, +5 boss).
    Aplica bônus extra de corrupção por mutações:
    - Marca Estelar Pulsante (id 14): +1 Corrupção extra
    - Centelha do Aspecto Desperto (id 20): +2 Corrupção extra
    Ao subir de estágio:
    - Sorteia 1 mutação.
    - Ao cruzar o limiar para o Estágio III (Possuído): sorteia +1 mutação extra garantida (total 2).
    Retorna (pontos_ganhos, nova_corrupcao, subiu_de_estagio).
    """
    pontos = PONTOS_CORRUPCAO_POR_PAPEL.get(monstro_papel, 2)
    extra_corr = 0
    try:
        mutacoes = getattr(player, "mutacoes", None)
        if mutacoes is None:
            mutacoes = session.query(PlayerMutacao).filter_by(player_id=player.id).all()
        for m in (mutacoes or []):
            mid = getattr(m, "mutacao_id", 0)
            if mid == 14:
                extra_corr += 1
            elif mid == 20:
                extra_corr += 2
    except Exception:
        pass

    pontos_totais = pontos + extra_corr
    corrupcao_antiga = player.corrupcao or 0
    estagio_antigo = estagio_corrupcao(corrupcao_antiga)

    nova_corrupcao = min(100, corrupcao_antiga + pontos_totais)
    player.corrupcao = nova_corrupcao

    novo_estagio = estagio_corrupcao(nova_corrupcao)
    subiu_de_estagio = novo_estagio > estagio_antigo

    if subiu_de_estagio and novo_estagio >= 1:
        try:
            sortear_mutacao(session, player)
            # Ao ENTRAR no Estágio 3 (Possuído): sortear 1 mutação garantida extra
            if estagio_antigo < 3 and novo_estagio >= 3:
                sortear_mutacao(session, player)
        except Exception:
            pass

    session.commit()
    return pontos_totais, nova_corrupcao, subiu_de_estagio
