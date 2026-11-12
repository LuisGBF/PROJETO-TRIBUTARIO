#!/usr/bin/env python3
"""Simulador de movimentação econômico-financeira de empresas.

Gera os lançamentos mensais (receita, folha, custos e despesas) de uma
carteira fixa de empresas reais, sorteadas da base pública do CNPJ da
Receita Federal. O cadastro é real (CNPJ, CNAE, setor, porte e opção pelo
Simples); os valores financeiros são fictícios e servem para demonstrar o
comparativo de regimes tributários do Projeto Integrado.

Cada empresa tem um perfil estável (tamanho e estrutura de custos), então
a mesma empresa aparece em todos os meses com valores coerentes entre si.
Parte dos registros recebe problemas de qualidade controlados, que serão
tratados na etapa de Análise Exploratória de Dados.
"""
import argparse
import csv
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np

CARTEIRA_PADRAO = Path(__file__).with_name("carteira_empresas.csv")

# Semente fixa dos perfis: garante que a mesma empresa tenha sempre
# o mesmo tamanho e a mesma estrutura de custos, em qualquer execução
SEMENTE_PERFIL = 2026

LIMITE_SIMPLES_ANUAL = 4_800_000
LIMITE_PRESUMIDO_ANUAL = 78_000_000

# Hipótese do simulador: a base pública não separa Lucro Presumido de Lucro Real,
# então parte das empresas fora do Simples é sorteada para o Lucro Real
PROB_LUCRO_REAL = 0.20

# Receita bruta anual por porte declarado na Receita Federal (em R$)
FAIXAS_PORTE = {
    "01": (81_000, 360_000),            # microempresa
    "03": (360_000, 4_800_000),         # empresa de pequeno porte
    "05": (4_800_000, 100_000_000),     # demais
}

# Estrutura de custos por setor, como fração da receita
SETORES = {
    "Comércio":  {"folha": (0.08, 0.15), "cmv": (0.50, 0.70)},
    "Serviços":  {"folha": (0.20, 0.45), "cmv": (0.00, 0.05)},
    "Indústria": {"folha": (0.12, 0.25), "cmv": (0.40, 0.60)},
}

# Fator de sazonalidade da receita por mês (janeiro a dezembro; 1 = mês típico)
SAZONALIDADE = {
    "Comércio":  [0.90, 0.90, 0.95, 0.95, 1.00, 0.95, 1.00, 1.00, 0.95, 1.00, 1.15, 1.30],
    "Serviços":  [1.00] * 12,
    "Indústria": [0.95, 0.95, 1.00, 1.00, 1.00, 1.00, 1.00, 1.05, 1.05, 1.05, 1.00, 0.95],
}

VARIANTES_SETOR = {
    "Comércio": ["COMERCIO", "comercio", "Com."],
    "Serviços": ["SERVICOS", "servico", "Serv."],
    "Indústria": ["INDUSTRIA", "industria", "Ind."],
}

CAMPOS = [
    "id_lancamento", "cnpj_basico", "competencia", "macro_setor",
    "cnae_fiscal_principal", "regime_atual", "receita_bruta_mensal",
    "folha_salarios_mensal", "custo_mercadoria_vendida",
    "despesas_operacionais", "compras_com_credito", "data_hora_geracao",
]


def ler_carteira(caminho):
    """Lê a carteira de empresas reais criada pelo criar_carteira.py."""
    with open(caminho, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def perfil_empresa(empresa):
    """Define o perfil estável da empresa: receita anual, regime e custos."""
    rng = np.random.default_rng([SEMENTE_PERFIL, int(empresa["cnpj_basico"])])
    optante = empresa["optante_simples"] == "S"

    porte = empresa["porte_empresa"]
    if optante and porte not in ("01", "03"):
        porte = "03"        # no Simples, a receita não passa de R$ 4,8 milhões
    elif porte not in FAIXAS_PORTE:
        porte = "05"        # porte não informado fora do Simples

    # Receita anual dentro da faixa do porte, mais concentrada na parte de baixo
    minimo, maximo = np.log(FAIXAS_PORTE[porte])
    receita_anual = float(np.exp(minimo + (maximo - minimo) * rng.beta(1.2, 3.0)))

    if optante:
        regime = "Simples Nacional"
    elif receita_anual > LIMITE_PRESUMIDO_ANUAL or rng.random() < PROB_LUCRO_REAL:
        regime = "Lucro Real"
    else:
        regime = "Lucro Presumido"

    custos = SETORES[empresa["macro_setor"]]
    return {
        "receita_anual": receita_anual,
        "regime": regime,
        "p_folha": rng.uniform(*custos["folha"]),
        "p_cmv": rng.uniform(*custos["cmv"]),
        "p_despesas": rng.uniform(0.10, 0.25),
        "p_credito": rng.uniform(0.3, 0.8),
    }


def gerar_registro(empresa, competencia, agora):
    """Gera o lançamento do mês para uma empresa da carteira."""
    perfil = perfil_empresa(empresa)
    ano, mes = map(int, competencia.split("-"))
    rng = np.random.default_rng([SEMENTE_PERFIL, int(empresa["cnpj_basico"]), ano, mes])

    base_mensal = perfil["receita_anual"] / 12
    sazonal = SAZONALIDADE[empresa["macro_setor"]][mes - 1]

    # Receita e custo variam com o mês; folha e despesas são mais estáveis
    receita = base_mensal * sazonal * rng.lognormal(0, 0.10)
    folha = base_mensal * perfil["p_folha"] * rng.normal(1, 0.02)
    cmv = receita * perfil["p_cmv"] * rng.normal(1, 0.05)
    despesas = base_mensal * perfil["p_despesas"] * rng.normal(1, 0.05)
    compras_credito = (cmv + despesas) * perfil["p_credito"]

    # O mesmo par empresa + competência gera sempre o mesmo identificador
    id_lancamento = uuid.uuid5(uuid.NAMESPACE_URL,
                               f"pipeline-tributario/{empresa['cnpj_basico']}/{competencia}")

    return {
        "id_lancamento": str(id_lancamento),
        "cnpj_basico": empresa["cnpj_basico"],
        "competencia": competencia,
        "macro_setor": empresa["macro_setor"],
        "cnae_fiscal_principal": empresa["cnae_fiscal_principal"],
        "regime_atual": perfil["regime"],
        "receita_bruta_mensal": round(receita, 2),
        "folha_salarios_mensal": round(folha, 2),
        "custo_mercadoria_vendida": round(max(cmv, 0), 2),
        "despesas_operacionais": round(despesas, 2),
        "compras_com_credito": round(compras_credito, 2),
        "data_hora_geracao": agora.isoformat(timespec="seconds"),
    }


def injetar_defeito(rng, reg):
    """Aplica um problema de qualidade controlado ao registro."""
    tipo = str(rng.choice(["ausente", "data", "numero", "categoria", "cnpj", "discrepante"]))

    if tipo == "ausente":
        campo = str(rng.choice(["folha_salarios_mensal", "despesas_operacionais",
                                "custo_mercadoria_vendida"]))
        reg[campo] = ""
    elif tipo == "data":
        reg["data_hora_geracao"] = datetime.fromisoformat(
            reg["data_hora_geracao"]).strftime("%d/%m/%Y %H:%M")
    elif tipo == "numero":
        reg["receita_bruta_mensal"] = f"{reg['receita_bruta_mensal']:.2f}".replace(".", ",")
    elif tipo == "categoria":
        reg["macro_setor"] = str(rng.choice(VARIANTES_SETOR[reg["macro_setor"]]))
    elif tipo == "cnpj":
        c = reg["cnpj_basico"]
        # Tirar os zeros só faz diferença quando o CNPJ começa com zero
        if c.startswith("0") and rng.random() < 0.5:
            reg["cnpj_basico"] = c.lstrip("0")
        else:
            reg["cnpj_basico"] = f"{c[:2]}.{c[2:5]}.{c[5:]}"
    elif tipo == "discrepante":
        valor = reg["receita_bruta_mensal"]
        reg["receita_bruta_mensal"] = -valor if rng.random() < 0.5 else round(valor * 1000, 2)

    return reg, tipo


def main():
    parser = argparse.ArgumentParser(
        description="Simulador de movimentação econômico-financeira de empresas")
    parser.add_argument("--carteira", default=str(CARTEIRA_PADRAO),
                        help="CSV com a carteira de empresas (padrão: carteira_empresas.csv)")
    parser.add_argument("--registros", type=int, default=None,
                        help="usar só as N primeiras empresas da carteira (padrão: todas)")
    parser.add_argument("--saida", default="dados",
                        help="diretório onde os arquivos CSV são gravados")
    parser.add_argument("--taxa-defeitos", type=float, default=0.10,
                        help="proporção de registros com problemas de qualidade, de 0 a 1")
    parser.add_argument("--competencia", default=None,
                        help="mês de referência no formato AAAA-MM (padrão: mês atual)")
    parser.add_argument("--semente", type=int, default=None,
                        help="semente aleatória dos defeitos, para reproduzir uma execução")
    args = parser.parse_args()

    carteira = ler_carteira(args.carteira)
    if args.registros is not None:
        if args.registros < 10:
            parser.error("o mínimo é de 10 registros por execução")
        carteira = carteira[:args.registros]
    if not 0 <= args.taxa_defeitos <= 1:
        parser.error("a taxa de defeitos deve estar entre 0 e 1")

    rng = np.random.default_rng(args.semente)
    agora = datetime.now()
    competencia = args.competencia or agora.strftime("%Y-%m")

    registros = [gerar_registro(empresa, competencia, agora) for empresa in carteira]

    # Problemas de qualidade controlados
    contagem = {}
    n_defeitos = round(len(registros) * args.taxa_defeitos)
    for i in rng.choice(len(registros), size=n_defeitos, replace=False):
        registros[i], tipo = injetar_defeito(rng, registros[i])
        contagem[tipo] = contagem.get(tipo, 0) + 1

    # Duplicidades: cópias exatas de registros existentes
    n_duplicados = max(1, n_defeitos // 5) if n_defeitos else 0
    for i in rng.choice(len(registros), size=n_duplicados, replace=False):
        registros.append(dict(registros[i]))
    if n_duplicados:
        contagem["duplicado"] = n_duplicados

    rng.shuffle(registros)

    # Um arquivo novo por execução: execuções anteriores nunca são sobrescritas
    destino = Path(args.saida)
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"movimentacao_{agora:%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:6]}.csv"

    with arquivo.open("w", newline="", encoding="utf-8") as f:
        escritor = csv.DictWriter(f, fieldnames=CAMPOS, lineterminator="\n")
        escritor.writeheader()
        escritor.writerows(registros)

    print(f"Arquivo gerado:      {arquivo}")
    print(f"Competência:         {competencia}")
    print(f"Empresas:            {len(carteira)}")
    print(f"Registros gravados:  {len(registros)}")
    print(f"Defeitos injetados:  {contagem if contagem else 'nenhum'}")


if __name__ == "__main__":
    main()
