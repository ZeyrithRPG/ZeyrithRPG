"""
Utilidades visuais compartilhadas — usadas por todos os handlers, pra manter
o HUD, o Mapa e o Combate com a mesma barra, sempre.
"""


def barra(atual, maximo, tamanho=10, cheio="🟩", vazio="⬛"):
    if not maximo:
        return vazio * tamanho
    n = round(tamanho * max(0, min(atual, maximo)) / maximo)
    return cheio * n + vazio * (tamanho - n)


def esc_md(texto) -> str:
    """Escapa com segurança caracteres especiais para Markdown V1 do Telegram (_ * ` [)."""
    if texto is None:
        return ""
    try:
        from telegram.helpers import escape_markdown
        return escape_markdown(str(texto), version=1)
    except ImportError:
        t = str(texto)
        for c in ("\\", "_", "*", "`", "["):
            t = t.replace(c, "\\" + c)
        return t



def formatar_bloco_corrupcao(corrupcao: int) -> str:
    """
    Item 11.1:
    ☣️ Corrupção: 47/100 (Estágio II — Corrompido)
       ⚔️ +10% Dano   🛡️ -2 Defesa   💉 -15% Cura Recebida
       💰 Purificar (-20 pontos): 113 de ouro
    """
    from game.corrupcao import estagio_corrupcao, ESTAGIOS, custo_purificacao
    corr = max(0, min(100, corrupcao or 0))
    est_idx = estagio_corrupcao(corr)
    est_data = ESTAGIOS.get(est_idx, ESTAGIOS[0])
    rotulo = est_data["estagio"]
    nome = est_data["nome"]
    custo = custo_purificacao(corr)

    # Modificadores
    dano_pct = round((est_data["mult_dano"] - 1.0) * 100)
    def_pts = est_data["bonus_defesa"]
    mod_cura = est_data["mod_cura"]
    cura_pct = round((1.0 - mod_cura) * 100)

    mods = []
    if dano_pct > 0:
        mods.append(f"⚔️ +{dano_pct}% Dano")
    if def_pts != 0:
        mods.append(f"🛡️ {def_pts} Defesa")
    if cura_pct > 0:
        mods.append(f"💉 -{cura_pct}% Cura Recebida")
    mods_str = "   ".join(mods) if mods else "Sem alterações"

    linhas = [
        f"☣️ *Corrupção:* {corr}/100 ({rotulo} — {nome})",
        f"   {mods_str}",
    ]
    if corr > 0:
        linhas.append(f"   💰 *Purificar (-20 pontos):* {custo} de ouro")
    return "\n".join(linhas)


def formatar_bloco_mutacoes(mutacoes: list) -> str:
    """
    Item 11.1:
    🧬 Mutações Ativas (2):
       • Couraça Escamosa de Ébano — 🛡️ +3 Defesa | ❌ -10% Fuga
       • Marca Estelar Pulsante — 🔮 +15 Mana Máx. | ❌ +1 Corrupção extra por derrota
    """
    if not mutacoes:
        return ""
    qtd = len(mutacoes)
    linhas = [f"🧬 *Mutações Ativas ({qtd}):*"]
    for m in mutacoes:
        nome = getattr(m, "nome", "Mutação")
        bonus = getattr(m, "bonus_mecanico", "Bônus ativo") or "Bônus ativo"
        penalidade = getattr(m, "penalidade", "Penalidade") or "Sem penalidade direta"
        ic_bonus = "🛡️"
        b_low = bonus.lower()
        if "mana" in b_low:
            ic_bonus = "🔮"
        elif "dano" in b_low or "ataque" in b_low or "atq" in b_low:
            ic_bonus = "⚔️"
        elif "ouro" in b_low:
            ic_bonus = "💰"
        elif "xp" in b_low:
            ic_bonus = "⭐"
        elif "crítico" in b_low or "critico" in b_low:
            ic_bonus = "🎯"
        linhas.append(f"   • *{esc_md(nome)}* — {ic_bonus} {esc_md(bonus)} | ❌ {esc_md(penalidade)}")
    return "\n".join(linhas)


def formatar_bloco_debuff(debuff_ativo: str) -> str:
    """
    Item 11.1:
    🩹 Status: Ferida Profunda ativa (-10% HP Máximo)
       Cure no Curandeiro da cidade.
    """
    if not debuff_ativo:
        return ""
    descricoes = {
        "Ferida Profunda": "-10% HP Máximo",
        "Tremor nos Braços": "-1 no Dano de arma",
        "Fadiga Persistente": "-10 Vigor Máximo",
        "Marca do Medo": "-5% Chance de Fuga",
    }
    desc = descricoes.get(debuff_ativo, "Penalidade física")
    instrucao = "Cure no Curandeiro da cidade." if debuff_ativo != "Marca do Medo" else "Vença um combate para dissipar o medo."
    return f"🩹 *Status:* {esc_md(debuff_ativo)} ativa ({esc_md(desc)})\n   {esc_md(instrucao)}"


def formatar_bloco_titulo(titulo_nome: str, session=None) -> str:
    """
    Item 11.8:
    🏅 Título Ativo: Veterano de Mil Batalhas
       +1% de Chance de Crítico
    """
    if not titulo_nome:
        return "🏅 *Título Ativo:* O Forasteiro\n   Sem bônus mecânico ativo"
    bonus_desc = "Sem bônus mecânico ativo"
    if session:
        from db.models import Titulo
        t_obj = session.query(Titulo).filter_by(nome=titulo_nome).first()
        if t_obj and t_obj.bonus:
            bonus_desc = t_obj.bonus
    else:
        mapa_titulos = {
            "Veterano de Mil Batalhas": "+1% de Chance de Crítico",
            "Açougueiro": "+2% de Chance de Crítico",
            "Sobrevivente Nato": "+5% de Chance de Fuga",
            "Ferreiro de Mão Cheia": "-10% no custo de reparo da arma",
            "Bolso Fundo": "+5% de ouro ganho em combates",
            "Mestre de Uma Só Arma": "+5% de Dano com arma",
        }
        bonus_desc = mapa_titulos.get(titulo_nome, bonus_desc)
    return f"🏅 *Título Ativo:* {esc_md(titulo_nome)}\n   {esc_md(bonus_desc)}"


def formatar_bloco_maestria(tipo_arma: str, nivel: int, nome_classe: str = "") -> str:
    """
    Item 11.2:
    ⚔️ Maestria: Machado — Nível 12/30
       💥 Dano Crítico: 2.15x   🎲 Chance de Drop: +4%
       🎯 Crítico: +1%   🔧 Reparo: -4% de custo
       📊 +12% de Dano (proficiência de arma)
    """
    from game.proficiencia import (
        bonus_mult_critico, bonus_drop_materiais_pct,
        bonus_critico_chance_pct, bonus_desconto_reparo_pct,
        bonus_dano_percentual, NIVEL_MAXIMO_PROFICIENCIA
    )
    nv = min(NIVEL_MAXIMO_PROFICIENCIA, max(0, nivel or 0))
    mult_crit = 2.0 + bonus_mult_critico(nv)
    drop_pct = int(bonus_drop_materiais_pct(nv))
    crit_pct = bonus_critico_chance_pct(nv)
    reparo_pct = int(round(bonus_desconto_reparo_pct(nv) * 100))
    dano_pct = int(round(bonus_dano_percentual(nv, nome_classe or "", tipo_arma or "") * 100))

    crit_str = f"{crit_pct:g}%"
    return (
        f"⚔️ *Maestria:* {esc_md(tipo_arma or 'Arma')} — Nível {nv}/{NIVEL_MAXIMO_PROFICIENCIA}\n"
        f"   💥 Dano Crítico: {mult_crit:.2f}x   🎲 Chance de Drop: +{drop_pct}%\n"
        f"   🎯 Crítico: +{crit_str}   🔧 Reparo: -{reparo_pct}% de custo\n"
        f"   📊 +{dano_pct}% de Dano (proficiência de arma)"
    )


def formatar_alerta_level_up_proficiencia(tipo_arma: str, nivel_novo: int) -> str:
    """
    Item 11.3:
    ⚔️ Sua maestria com Machado evoluiu para o Nível 12!
    🎲 +1% Chance de Drop   🔧 -2% custo de Reparo
    """
    from game.proficiencia import obter_trilhas_desbloqueadas_nivel
    trilhas = obter_trilhas_desbloqueadas_nivel(nivel_novo)
    trilhas_txt = "   ".join(trilhas) if trilhas else "✨ Maestria aprimorada!"
    return (
        f"⚔️ *Sua maestria com {esc_md(tipo_arma)} evoluiu para o Nível {nivel_novo}!*"
        f"\n{trilhas_txt}"
    )


def formatar_critico_combate(mult_critico: float, dano_total: int) -> str:
    """
    Item 11.4:
    💥 CRÍTICO! Dano multiplicado por 2.15x — 13 de dano total!
    """
    return f"💥 *CRÍTICO! Dano multiplicado por {mult_critico:.2f}x — {dano_total} de dano total!*"


def formatar_resumo_derrota(
    nome_monstro: str, ouro_perdido: int, pontos_corr: int,
    corr_anterior: int, nova_corrupcao: int, subiu_estagio: bool = False,
    debuff_sorteado: str = None
) -> str:
    """
    Item 11.5:
    ☠️ Você caiu diante do Corvo Sanguinário...
    💰 Perdeu 15 de ouro.
    ☣️ +3 de Corrupção (47 → 50, Estágio II mantido)
    🩹 Você sofreu uma Ferida Profunda! (-10% HP Máximo até ser curado)
    """
    from game.corrupcao import estagio_corrupcao, ESTAGIOS
    est_num = estagio_corrupcao(nova_corrupcao)
    romano = ESTAGIOS[est_num]["estagio"].replace("Estágio ", "")
    nome_est = ESTAGIOS[est_num]["nome"]
    est_status = f"Estágio {romano} mantido" if not subiu_estagio else f"Subiu para o Estágio {romano} — {nome_est}!"

    linhas = [
        f"☠️ *Você caiu diante do {esc_md(nome_monstro)}...*",
        f"💰 Perdeu {ouro_perdido} de ouro.",
        f"☣️ +{pontos_corr} de Corrupção ({corr_anterior} → {nova_corrupcao}, {est_status})",
    ]
    if debuff_sorteado:
        desc_map = {
            "Ferida Profunda": "-10% HP Máximo até ser curado",
            "Tremor nos Braços": "-1 de Dano com armas até ser curado",
            "Fadiga Persistente": "-10 Vigor Máximo até ser curado",
            "Marca do Medo": "-5% Chance de Fuga (curada ao vencer o próximo combate)",
        }
        desc = desc_map.get(debuff_sorteado, "Sequela física até ser curado")
        linhas.append(f"🩹 *Você sofreu uma {esc_md(debuff_sorteado)}!* ({esc_md(desc)})")
    return "\n".join(linhas)


def formatar_item_arma(nome: str, dano: int, tipo: str, chance: float = 0.0, efeito: str = None, valor: float = 0.0) -> str:
    """
    Item 11.7:
    🪓 Machado de Ferro Forjado
       Dano: 8   Tipo: Machado
       ✨ 15% de chance: Sangramento (2 turnos)
    """
    from handlers.comercio import _icone_tipo
    icone = _icone_tipo(tipo)
    linhas = [
        f"{icone} *{esc_md(nome)}*",
        f"   Dano: *{dano}*   Tipo: *{esc_md(tipo)}*",
    ]
    if efeito:
        if chance > 0:
            val_txt = f" ({int(valor)} turnos)" if valor > 0 and "turno" not in efeito.lower() else ""
            linhas.append(f"   ✨ *{int(chance)}% de chance:* {esc_md(efeito)}{val_txt}")
        else:
            linhas.append(f"   ✨ *Efeito:* {esc_md(efeito)}")
    return "\n".join(linhas)
