"""
Modelos do banco de dados — A Infecção que Segura o Mundo

Duas famílias de tabela, bem separadas:
1. REFERÊNCIA (game rules) — vem da planilha, é igual pra todo mundo, só muda quando
   o jogo é rebalanceado. Nunca é escrita durante o jogo, só lida.
2. JOGADOR (player state) — o progresso de cada pessoa. É o que precisa ficar salvo
   pra sempre no Neon (o banco permanente), nunca no disco do Render.
"""
from sqlalchemy import (
    Column, Integer, String, Float, Text, ForeignKey, DateTime, Boolean, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime

Base = declarative_base()


# ============================================================
# REFERÊNCIA — importado da planilha, nunca alterado em jogo
# ============================================================

class Tier(Base):
    __tablename__ = "ref_tiers"
    id = Column(Integer, primary_key=True)
    nome = Column(String, unique=True, nullable=False)
    nivel_min = Column(Integer)
    nivel_max = Column(Integer)
    nivel_ref = Column(Integer)
    cor_hex = Column(String)
    dano_comum = Column(Integer)
    dano_raro = Column(Integer)
    dano_lendario = Column(Integer)
    historia = Column(Text)


class CurvaMestra(Base):
    __tablename__ = "ref_curva_mestra"
    nivel = Column(Integer, primary_key=True)
    hp = Column(Integer)
    dano_arma_padrao = Column(Integer)
    defesa_esperada = Column(Integer)
    atq_bonus = Column(Integer)
    mana = Column(Integer)
    hp_comum = Column(Integer)
    hp_elite = Column(Integer)
    hp_boss = Column(Integer)
    hp_cosmico = Column(Integer)
    xp_prox_nivel = Column(Integer)


class Classe(Base):
    __tablename__ = "ref_classes"
    id = Column(Integer, primary_key=True)
    nome = Column(String, unique=True, nullable=False)
    atributo_primario = Column(String)
    passiva_unica = Column(Text)
    status_iniciais = Column(String)
    kit_inicial = Column(Text)
    proficiencia_inicial = Column(Integer, default=10)
    vantagem = Column(Text)
    desvantagem = Column(Text)


class TalentoClasse(Base):
    __tablename__ = "ref_talentos_classe"
    id = Column(Integer, primary_key=True)
    classe_nome = Column(String, nullable=False)
    nivel = Column(Integer)
    nome = Column(String)
    efeito = Column(Text)
    mestre = Column(String)


class Arma(Base):
    __tablename__ = "ref_armas"
    id = Column(Integer, primary_key=True)
    tier = Column(String)
    tipo = Column(String)
    variacao = Column(String, nullable=False)
    efeito_especial = Column(String)
    lore = Column(Text)
    mod_variacao = Column(Float)
    dano_comum = Column(Integer)
    dano_raro = Column(Integer)
    preco_compra = Column(Integer)
    preco_venda_mercador = Column(Integer)


class Armadura(Base):
    __tablename__ = "ref_armaduras"
    id = Column(Integer, primary_key=True)
    tier = Column(String)
    slot = Column(String)
    variacao = Column(String, nullable=False)
    efeito_especial = Column(String)
    lore = Column(Text)
    mod_variacao = Column(Float)
    defesa_comum = Column(Integer)
    defesa_raro = Column(Integer)
    preco_compra = Column(Integer)
    preco_venda_mercador = Column(Integer)


class Monstro(Base):
    __tablename__ = "ref_bestiario"
    id = Column(Integer, primary_key=True)
    tier = Column(String)
    nome = Column(String, nullable=False)
    papel = Column(String)  # Comum / Elite / Boss / Cosmico
    nivel = Column(Integer)
    hp = Column(Integer)
    dano = Column(Integer)
    defesa = Column(Integer)
    atq_bonus = Column(Integer)
    golpe_especial = Column(String)
    efeito_mecanico = Column(Text)
    motivacao = Column(Text)
    fraqueza = Column(Text)
    materiais_dropados = Column(Text)
    papel_combate = Column(String)  # DPS/Tanque/Suporte/Nao-hostil/Necrofago/etc
    interacao_ambiental = Column(Text)  # "Se abordado em paz, pode ser poupado..."
    loot_unico = Column(Text)  # item exclusivo de Boss/Nomeado


class Missao(Base):
    __tablename__ = "ref_missoes"
    id = Column(Integer, primary_key=True)
    tier = Column(String)
    nome = Column(String)
    tipo = Column(String)
    objetivo = Column(Text)
    recompensa = Column(Text)
    faccao_afetada = Column(String)
    pontos_reputacao = Column(String)
    is_principal = Column(Boolean, default=False)  # fecha o tier e libera o proximo
    nivel_sugerido = Column(Integer)
    recompensa_xp = Column(Integer)
    categoria = Column(String)  # Combate/Coleta/Elite/Social/Exploracao/Crafting
    requisito_honra = Column(String)  # Comum (0) / Veterano (50) / Lendario (100)
    npc_fonte = Column(String)  # quem da a missao
    requisito_especial = Column(Text)  # ex: "Completar X antes"
    recompensa_extra = Column(Text)  # alem do Ouro


class Material(Base):
    __tablename__ = "ref_materiais"
    id = Column(Integer, primary_key=True)
    tier = Column(String)
    nome = Column(String, nullable=False)
    categoria = Column(String)
    bioma = Column(String)
    cd_coleta = Column(String)
    preco_base = Column(Integer)
    lore = Column(Text)
    icone = Column(String)
    raridade = Column(String)  # ex: "Comum (Alto rendimento)"
    uso_principal = Column(Text)  # receita que usa, ou "Venda (sem receita)"


class Local(Base):
    __tablename__ = "ref_locais"
    id = Column(Integer, primary_key=True)
    nome = Column(String, unique=True, nullable=False)
    tipo = Column(String)  # Cidade / Covil de Boss / Local Secreto / Estrada Perigosa / etc
    cidade_proxima = Column(String)
    nivel_ref = Column(Integer)
    descricao = Column(Text)
    perigo = Column(Integer)
    o_que_tem = Column(Text)  # monstros/materiais/gatilho de descoberta associados


class Receita(Base):
    __tablename__ = "ref_receitas"
    id = Column(Integer, primary_key=True)
    tier = Column(String)
    tipo_slot = Column(String, nullable=False)  # ex: "Espada", "Amuleto do Uivo"
    material_base_1 = Column(String)
    material_base_2 = Column(String)
    custo_base_ouro = Column(Integer)
    essencia_nivel2 = Column(String)
    custo_nivel2_ouro = Column(Integer)
    artesao_mestre = Column(String)
    categoria = Column(String)  # Arma/Armadura ou Acessório
    efeito = Column(Text)  # Acessorio: efeito do item. Arma/Armadura: local de forja (ex: "Forja")


class Magia(Base):
    __tablename__ = "ref_magias"
    id = Column(Integer, primary_key=True)
    nome = Column(String, unique=True)
    elemento = Column(String)
    grau = Column(String)  # Basico / Avancado / Mestre
    nivel_minimo = Column(Integer)
    custo_mana = Column(Integer)
    dano = Column(Integer)
    efeito = Column(Text)
    lore = Column(Text)


# ============================================================
# JOGADOR — progresso real, precisa persistir pra sempre (Neon)
# ============================================================

class Player(Base):
    __tablename__ = "players"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    nome_personagem = Column(String)
    classe_id = Column(Integer, ForeignKey("ref_classes.id"))
    nivel = Column(Integer, default=1)
    xp_atual = Column(Integer, default=0)
    hp_atual = Column(Integer)
    hp_max = Column(Integer)
    vig_atual = Column(Integer)
    vig_max = Column(Integer)
    mana_atual = Column(Integer)
    mana_max = Column(Integer)
    ouro = Column(Integer, default=0)
    atributo_for = Column(Integer, default=10)
    atributo_des = Column(Integer, default=10)
    atributo_con = Column(Integer, default=10)
    atributo_int = Column(Integer, default=10)
    atributo_sab = Column(Integer, default=10)
    atributo_car = Column(Integer, default=10)
    pontos_atributo_disponiveis = Column(Integer, default=0)  # pro sistema de distribuicao manual, futuro
    tier_mais_alto_alcancado = Column(Integer, default=1)
    hora_do_mundo = Column(Integer, default=8)  # relogio do sistema de Tempo, 0-23
    corrupcao = Column(Integer, default=0)  # 0-100, Estagios da Infeccao
    local_atual = Column(String, default="Vila Inicial")
    em_combate_monstro_id = Column(Integer, nullable=True)
    em_combate_hp_monstro = Column(Integer, nullable=True)
    em_combate_efeito_monstro = Column(String, nullable=True)
    em_combate_efeito_monstro_turnos = Column(Integer, nullable=True)
    em_combate_efeito_jogador = Column(String, nullable=True)
    em_combate_efeito_jogador_turnos = Column(Integer, nullable=True)
    loot_pendente = Column(Text, nullable=True)  # JSON com materiais esperando "Lootear"
    monstros_poupados = Column(Text, nullable=True)  # nomes curtos separados por "|"
    criado_em = Column(DateTime, default=datetime.utcnow)

    classe = relationship("Classe")
    inventario = relationship("PlayerInventario", back_populates="player")
    proficiencias = relationship("PlayerProficiencia", back_populates="player")


class PlayerInventario(Base):
    __tablename__ = "player_inventario"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    tipo_item = Column(String)  # arma / armadura / material / consumivel / ferramenta
    item_ref_id = Column(Integer)
    nome_item = Column(String)
    quantidade = Column(Integer, default=1)
    equipado = Column(Boolean, default=False)

    player = relationship("Player", back_populates="inventario")


class PlayerProficiencia(Base):
    __tablename__ = "player_proficiencias"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    tipo_arma = Column(String)
    valor = Column(Integer, default=0)

    player = relationship("Player", back_populates="proficiencias")
    __table_args__ = (UniqueConstraint("player_id", "tipo_arma"),)


class PlayerReputacaoFaccao(Base):
    __tablename__ = "player_reputacao_faccao"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    faccao = Column(String)
    pontos = Column(Integer, default=0)
    __table_args__ = (UniqueConstraint("player_id", "faccao"),)


class PlayerQuest(Base):
    __tablename__ = "player_quests"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    quest_id = Column(Integer, ForeignKey("ref_missoes.id"))
    status = Column(String, default="disponivel")  # disponivel / em_andamento / concluida


class PlayerTalento(Base):
    __tablename__ = "player_talentos"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    talento_id = Column(Integer, ForeignKey("ref_talentos_classe.id"))
    aprendido = Column(Boolean, default=False)


class PlayerKnowledge(Base):
    __tablename__ = "player_knowledge"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    monstro_id = Column(Integer, ForeignKey("ref_bestiario.id"))
    nivel_knowledge = Column(Integer, default=0)
    __table_args__ = (UniqueConstraint("player_id", "monstro_id"),)


class Titulo(Base):
    __tablename__ = "ref_titulos"
    id = Column(Integer, primary_key=True)
    nome = Column(String, unique=True, nullable=False)
    condicao = Column(Text)
    bonus = Column(Text)


class PlayerTitulo(Base):
    __tablename__ = "player_titulos"
    id = Column(Integer, primary_key=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    titulo_id = Column(Integer, ForeignKey("ref_titulos.id"))
    data_conquista = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("player_id", "titulo_id"),)
