"""
Exporta a planilha balanceamento_rpg-13.xlsx pro data/game_data.json.

Le a versao RECALCULADA (valores, nao formula) pra pegar HP/Dano/Defesa
ja computados pela Curva Mestra. Roda com: python3 db/export_json.py
"""
import json
import os
import re
import subprocess
import tempfile
import openpyxl

RAIZ = os.path.join(os.path.dirname(__file__), "..")
PLANILHA = os.path.join(RAIZ, "balanceamento_rpg-13.xlsx")
SAIDA = os.path.join(RAIZ, "data", "game_data.json")

TIERS_ORDEM = [
    "Sucata Enferrujada", "Bronze", "Ferro", "Prata", "Aço Élfico",
    "Mecanismo Anão", "Vidro Vulcânico", "Ferro Órquico", "Mithril",
    "Ébano", "Adamantina", "Osso de Dragão", "Pacto Daédrico",
    "Estelar / Cósmico",
]


def recalcular():
    """Usa LibreOffice headless pra recalcular formulas antes de ler."""
    tmpdir = tempfile.mkdtemp()
    subprocess.run(
        ["soffice", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", tmpdir, PLANILHA],
        check=True, capture_output=True, timeout=250,
    )
    caminho = os.path.join(tmpdir, os.path.basename(PLANILHA))
    return openpyxl.load_workbook(caminho, data_only=True)


def v(ws, r, c):
    val = ws.cell(row=r, column=c).value
    return val


def extrair_tiers(wb):
    ws = wb["Tiers"]
    out = []
    for r in range(9, 23):
        nome = v(ws, r, 2)
        if not nome:
            continue
        out.append({
            "nome": nome, "nivel_min": v(ws, r, 3), "nivel_max": v(ws, r, 4),
            "nivel_ref": v(ws, r, 5), "cor_hex": v(ws, r, 6),
            "dano_comum": v(ws, r, 7), "dano_raro": v(ws, r, 8), "dano_lendario": v(ws, r, 9),
        })
    return out


def extrair_curva_mestra(wb):
    ws = wb["Curva Mestra"]
    out = []
    for r in range(20, 95):
        nivel = v(ws, r, 1)
        if nivel is None:
            continue
        out.append({
            "nivel": nivel, "hp": v(ws, r, 2), "dano_arma_padrao": v(ws, r, 3),
            "defesa_esperada": v(ws, r, 4), "atq_bonus": v(ws, r, 5), "mana": None,
            "hp_comum": v(ws, r, 6), "hp_elite": v(ws, r, 7), "hp_boss": v(ws, r, 8),
            "hp_cosmico": v(ws, r, 9), "xp_prox_nivel": v(ws, r, 10),
        })
    return out


def extrair_bestiario(wb):
    ws = wb["Bestiario"]
    out = []
    for r in range(12, 482):
        nome = v(ws, r, 2)
        if not nome:
            continue
        out.append({
            "tier": v(ws, r, 1), "nome": nome, "papel": v(ws, r, 3), "nivel": v(ws, r, 4),
            "hp": v(ws, r, 5), "dano": v(ws, r, 6), "defesa": v(ws, r, 7),
            "atq_bonus": v(ws, r, 19), "golpe_especial": v(ws, r, 9),
            "efeito_mecanico": v(ws, r, 10), "motivacao": v(ws, r, 11),
            "fraqueza": v(ws, r, 21), "materiais_dropados": v(ws, r, 20),
            "papel_combate": v(ws, r, 22), "interacao_ambiental": v(ws, r, 25),
            "loot_unico": v(ws, r, 27),
        })
    return out


def extrair_locais(wb):
    ws = wb["Mundo - Locais"]
    out = []
    for r in range(5, 60):
        nome = v(ws, r, 1)
        if not nome:
            continue
        nivel_raw = v(ws, r, 7)
        try:
            nivel_ref = int(nivel_raw)
        except (TypeError, ValueError):
            nivel_ref = None
        out.append({
            "nome": nome, "tipo": v(ws, r, 2), "cidade_proxima": v(ws, r, 3),
            "nivel_ref": nivel_ref, "descricao": v(ws, r, 6), "perigo": v(ws, r, 12),
            "o_que_tem": v(ws, r, 5),
        })
    return out


def extrair_magias(wb):
    ws = wb["Magia e Habilidades"]
    out = []
    for r in range(18, 37):
        nome = v(ws, r, 1)
        if not nome or not isinstance(nome, str):
            continue
        out.append({
            "nome": nome, "elemento": v(ws, r, 2), "grau": v(ws, r, 3),
            "nivel_minimo": v(ws, r, 4), "custo_mana": v(ws, r, 5),
            "dano": v(ws, r, 7), "efeito": v(ws, r, 8), "lore": v(ws, r, 9),
        })
    return out


def extrair_classes(wb):
    ws = wb["Classes e Arquétipos"]
    out = []
    for r in range(3, 11):
        nome = v(ws, r, 2)
        if not nome:
            continue
        out.append({
            "nome": nome, "atributo_primario": v(ws, r, 4),
            "passiva_unica": v(ws, r, 6), "status_iniciais": v(ws, r, 11),
            "kit_inicial": v(ws, r, 12), "proficiencia_inicial": v(ws, r, 13),
            "vantagem": v(ws, r, 15), "desvantagem": v(ws, r, 16),
        })
    return out


def extrair_talentos(wb):
    ws = wb["Talentos de Classe"]
    out = []
    for r in range(5, 60):
        classe = v(ws, r, 1)
        if not classe:
            continue
        out.append({
            "classe_nome": classe, "nivel": v(ws, r, 2), "nome": v(ws, r, 3),
            "efeito": v(ws, r, 4), "mestre": v(ws, r, 5),
        })
    return out


def _preco_compra_venda(preco_venda_base):
    if not isinstance(preco_venda_base, (int, float)):
        return None, None
    compra = round(preco_venda_base * 1.5)
    venda_mercador = round(compra * 0.4)
    return compra, venda_mercador


def extrair_armas(wb):
    ws = wb["Armas"]
    out = []
    for r in range(15, 325):
        variacao = v(ws, r, 3)
        tier = v(ws, r, 1)
        if not variacao or not tier or tier == "Tier":
            continue
        compra, venda = _preco_compra_venda(v(ws, r, 12))
        out.append({
            "tier": tier, "tipo": v(ws, r, 2), "variacao": variacao,
            "efeito_especial": v(ws, r, 4), "lore": v(ws, r, 5),
            "mod_variacao": v(ws, r, 11), "dano_comum": v(ws, r, 9),
            "dano_raro": v(ws, r, 10), "preco_compra": compra,
            "preco_venda_mercador": venda,
        })
    return out


def extrair_armaduras(wb):
    ws = wb["Armaduras"]
    out = []
    for r in range(25, 325):
        variacao = v(ws, r, 3)
        tier = v(ws, r, 1)
        if not variacao or not tier or tier == "Tier":
            continue
        compra, venda = _preco_compra_venda(v(ws, r, 12))
        out.append({
            "tier": tier, "slot": v(ws, r, 2), "variacao": variacao,
            "efeito_especial": v(ws, r, 4), "lore": v(ws, r, 5),
            "mod_variacao": v(ws, r, 11), "defesa_comum": v(ws, r, 9),
            "defesa_raro": v(ws, r, 10), "preco_compra": compra,
            "preco_venda_mercador": venda,
        })
    return out


def extrair_missoes(wb):
    ws = wb["Missoes"]
    out = []
    NAO_MISSAO = {"Modesta", "Gente Humilde", "Preparo", "Significativa",
                  "Definidora de Tier", "Tier", None}
    for r in range(16, 260):
        tier = v(ws, r, 1)
        nome = v(ws, r, 2)
        if not tier or not nome or tier in NAO_MISSAO:
            continue
        if isinstance(tier, str) and "REFERENCIA" in tier:
            continue
        is_principal = r <= 29
        item = {
            "tier": tier, "nome": nome, "objetivo": v(ws, r, 4),
            "is_principal": is_principal,
            "categoria": v(ws, r, 9), "requisito_honra": v(ws, r, 10),
            "npc_fonte": v(ws, r, 11), "requisito_especial": v(ws, r, 12),
            "recompensa_extra": v(ws, r, 13),
        }
        if is_principal:
            item["nivel_sugerido"] = v(ws, r, 3)
            item["recompensa"] = v(ws, r, 5)  # Ouro
            item["recompensa_xp"] = v(ws, r, 6)
            item["recompensa_extra"] = v(ws, r, 7)  # item, sobrescreve o None acima
            item["tipo"] = "Principal"
        else:
            item["tipo"] = v(ws, r, 9)
            item["recompensa"] = v(ws, r, 5)
        out.append(item)
    return out


def extrair_materiais(wb):
    ws = wb["Recursos Naturais"]
    out = []
    for r in range(2, 700):
        nome = v(ws, r, 3)
        if not nome:
            continue
        out.append({
            "tier": v(ws, r, 2), "nome": nome, "categoria": v(ws, r, 4),
            "bioma": v(ws, r, 5), "cd_coleta": v(ws, r, 7),
            "preco_base": v(ws, r, 10) if isinstance(v(ws, r, 10), (int, float)) else None,
            "lore": v(ws, r, 11), "icone": v(ws, r, 13),
            "raridade": v(ws, r, 8), "uso_principal": v(ws, r, 9),
        })
    return out


def extrair_receitas(wb):
    ws = wb["Crafting - Receitas"]
    out = []
    for r in range(5, 600):
        tipo_slot = v(ws, r, 2)
        tier_bruto = v(ws, r, 1)
        if not tipo_slot or not tier_bruto:
            continue
        m = re.search(r"\((.+?)\)", tier_bruto)
        tier = m.group(1) if m else tier_bruto
        custo_nv2 = v(ws, r, 7)
        out.append({
            "tier": tier, "tipo_slot": tipo_slot,
            "material_base_1": v(ws, r, 3), "material_base_2": v(ws, r, 4),
            "custo_base_ouro": v(ws, r, 5) if isinstance(v(ws, r, 5), (int, float)) else None,
            "essencia_nivel2": v(ws, r, 6),
            "custo_nivel2_ouro": custo_nv2 if isinstance(custo_nv2, (int, float)) else None,
            "artesao_mestre": v(ws, r, 8), "categoria": v(ws, r, 9),
            "efeito": v(ws, r, 10),
        })
    return out


def extrair_titulos(wb):
    ws = wb["Titulos"]
    out = []
    for r in range(5, 25):
        nome = v(ws, r, 1)
        if not nome or not isinstance(nome, str) or len(nome) < 3:
            continue
        out.append({"nome": nome, "condicao": v(ws, r, 2), "bonus": v(ws, r, 3)})
    return out


def main():
    print("Recalculando planilha com LibreOffice...")
    wb = recalcular()

    dados = {
        "tiers": extrair_tiers(wb),
        "curva_mestra": extrair_curva_mestra(wb),
        "armas": extrair_armas(wb),
        "armaduras": extrair_armaduras(wb),
        "bestiario": extrair_bestiario(wb),
        "classes": extrair_classes(wb),
        "talentos_classe": extrair_talentos(wb),
        "locais": extrair_locais(wb),
        "magias": extrair_magias(wb),
        "missoes": extrair_missoes(wb),
        "materiais": extrair_materiais(wb),
        "receitas": extrair_receitas(wb),
        "titulos": extrair_titulos(wb),
    }

    os.makedirs(os.path.dirname(SAIDA), exist_ok=True)
    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)

    print("Exportado com sucesso:")
    for k, val in dados.items():
        print(f"  {k}: {len(val)}")


if __name__ == "__main__":
    main()
