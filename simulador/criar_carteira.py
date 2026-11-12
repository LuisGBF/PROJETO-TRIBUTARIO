#!/usr/bin/env python3
"""Cria a carteira de empresas reais usada pelo simulador.

Lê o recorte da base pública do CNPJ (Receita Federal), gerado no notebook
do Colab, e sorteia uma amostra de empresas de Comércio, Serviços e Indústria.
A carteira guarda só dados cadastrais públicos; os valores financeiros
continuam sendo gerados pelo simulador.
"""
import argparse

import pandas as pd

COLUNAS = ["cnpj_basico", "cnae_fiscal_principal", "macro_setor",
           "porte_empresa", "enquadramento"]
SETORES = ["Comércio", "Serviços", "Indústria"]


def codigo(serie, digitos):
    """Converte um código para texto com zeros à esquerda (ex.: 1 -> '01')."""
    return (serie.astype(str)
                 .str.replace(r"\.0$", "", regex=True)
                 .str.zfill(digitos))


def main():
    parser = argparse.ArgumentParser(description="Cria a carteira de empresas do simulador")
    parser.add_argument("recorte", help="arquivo Parquet com o recorte da base do CNPJ")
    parser.add_argument("--tamanho", type=int, default=1000,
                        help="quantidade de empresas na carteira")
    parser.add_argument("--semente", type=int, default=2026,
                        help="semente do sorteio, para repetir a mesma carteira")
    parser.add_argument("--saida", default="carteira_empresas.csv",
                        help="arquivo CSV gerado")
    args = parser.parse_args()

    base = pd.read_parquet(args.recorte, columns=COLUNAS)
    base = base[base["macro_setor"].isin(SETORES)].dropna(subset=["cnpj_basico"])

    carteira = base.sample(n=args.tamanho, random_state=args.semente)
    carteira = (carteira
                .assign(cnpj_basico=codigo(carteira["cnpj_basico"], 8),
                        cnae_fiscal_principal=codigo(carteira["cnae_fiscal_principal"], 7),
                        porte_empresa=codigo(carteira["porte_empresa"].fillna("00"), 2),
                        optante_simples=(carteira["enquadramento"] == "Simples Nacional")
                                        .map({True: "S", False: "N"}))
                .drop(columns="enquadramento")
                .sort_values("cnpj_basico"))

    carteira.to_csv(args.saida, index=False)

    print(f"Empresas no recorte (3 setores): {len(base):,}")
    print(f"Empresas na carteira:            {len(carteira):,}")
    print(f"Arquivo gerado:                  {args.saida}\n")
    print(carteira["macro_setor"].value_counts().to_string(), "\n")
    print(carteira["porte_empresa"].value_counts().sort_index().to_string(), "\n")
    print(carteira["optante_simples"].value_counts().to_string())


if __name__ == "__main__":
    main()
