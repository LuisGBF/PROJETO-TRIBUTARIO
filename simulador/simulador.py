#!/usr/bin/env python3
"""Simulador de movimentação econômico-financeira de empresas.

Gera lançamentos mensais fictícios (receita, folha, custos e despesas)
usados no comparativo de regimes tributários do Projeto Integrado.
Parte dos registros recebe problemas de qualidade controlados, que serão
tratados na etapa de Análise Exploratória de Dados.
"""
import argparse
import csv
import uuid
from datetime import datetime
from pathlib import Path

import numpy as np

LIMITE_SIMPLES_ANUAL = 4_800_000

# Parâmetros por setor: CNAEs observados na análise exploratória,
# receita mensal mediana e faixas de folha e custo como fração da receita
SETORES = {
    "Comércio": {
        "cnaes": ["4781400", "4712100", "4789099"],
        "receita_mediana": 60_000, "folha": (0.08, 0.15), "cmv": (0.50, 0.70),
    },
    "Serviços": {
        "cnaes": ["7020400", "6204000", "8630503", "9602501", "6911701"],
        "receita_mediana": 40_000, "folha": (0.20, 0.45), "cmv": (0.00, 0.05),
    },
    "Indústria": {
        "cnaes": ["1091102", "2539001", "3101200"],
        "receita_mediana": 120_000, "folha": (0.12, 0.25), "cmv": (0.40, 0.60),
    },
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


def gerar_registro(rng, competencia, agora):
    """Gera um lançamento mensal válido para uma empresa fictícia."""
    setor = str(rng.choice(list(SETORES)))
    p = SETORES[setor]

    # Faturamento segue distribuição log-normal: muitas empresas pequenas, poucas grandes
    receita = float(rng.lognormal(np.log(p["receita_mediana"]), 0.9))
    folha = receita * rng.uniform(*p["folha"])
    cmv = receita * rng.uniform(*p["cmv"])
    despesas = receita * rng.uniform(0.10, 0.25)
    compras_credito = (cmv + despesas) * rng.uniform(0.3, 0.8)

    if receita * 12 > LIMITE_SIMPLES_ANUAL:
        regime = str(rng.choice(["Lucro Presumido", "Lucro Real"], p=[0.6, 0.4]))
    else:
        regime = str(rng.choice(["Simples Nacional", "Lucro Presumido"], p=[0.8, 0.2]))

    return {
        "id_lancamento": str(uuid.uuid4()),
        "cnpj_basico": f"{int(rng.integers(0, 10**8)):08d}",
        "competencia": competencia,
        "macro_setor": setor,
        "cnae_fiscal_principal": str(rng.choice(p["cnaes"])),
        "regime_atual": regime,
        "receita_bruta_mensal": round(receita, 2),
        "folha_salarios_mensal": round(folha, 2),
        "custo_mercadoria_vendida": round(cmv, 2),
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
        reg["cnpj_basico"] = f"{c[:2]}.{c[2:5]}.{c[5:]}" if rng.random() < 0.5 else str(int(c))
    elif tipo == "discrepante":
        valor = reg["receita_bruta_mensal"]
        reg["receita_bruta_mensal"] = -valor if rng.random() < 0.5 else round(valor * 1000, 2)

    return reg, tipo


def main():
    parser = argparse.ArgumentParser(
        description="Simulador de movimentação econômico-financeira de empresas")
    parser.add_argument("--registros", type=int, default=50,
                        help="quantidade de registros por execução (mínimo 10)")
    parser.add_argument("--saida", default="dados",
                        help="diretório onde os arquivos CSV são gravados")
    parser.add_argument("--taxa-defeitos", type=float, default=0.10,
                        help="proporção de registros com problemas de qualidade, de 0 a 1")
    parser.add_argument("--competencia", default=None,
                        help="mês de referência no formato AAAA-MM (padrão: mês atual)")
    parser.add_argument("--semente", type=int, default=None,
                        help="semente aleatória para reproduzir uma execução")
    args = parser.parse_args()

    if args.registros < 10:
        parser.error("o mínimo é de 10 registros por execução")
    if not 0 <= args.taxa_defeitos <= 1:
        parser.error("a taxa de defeitos deve estar entre 0 e 1")

    rng = np.random.default_rng(args.semente)
    agora = datetime.now()
    competencia = args.competencia or agora.strftime("%Y-%m")

    registros = [gerar_registro(rng, competencia, agora) for _ in range(args.registros)]

    # Problemas de qualidade controlados
    contagem = {}
    n_defeitos = round(args.registros * args.taxa_defeitos)
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
    print(f"Registros gravados:  {len(registros)}")
    print(f"Defeitos injetados:  {contagem if contagem else 'nenhum'}")


if __name__ == "__main__":
    main()
