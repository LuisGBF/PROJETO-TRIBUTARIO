"""Cálculo tributário estimado por empresa e modelo estrela.

Entrada:
  /dados/tratados/movimentacao_tratada.csv        saída da limpeza em R
  /dados/cnpj_sp_recorte_tributario_spark.parquet  recorte da Receita (gerado pelo converter.py)
  parametros/simples_nacional.csv                 tabelas do Simples Nacional

Saída, em /dados/analitico:
  dim_empresa/, dim_tempo/, fato_movimentacao/    modelo estrela, em Parquet
  simulacao_tributaria/                           uma linha por empresa, em Parquet
  simulacao_tributaria.csv                        a mesma tabela em CSV, para o Colab

Os valores são estimativas simplificadas para comparar regimes, e não o cálculo fiscal oficial.
"""
import glob
import os
import shutil

from pyspark.sql import SparkSession, functions as F, types as T

DADOS = os.environ.get("DADOS", "/dados")
SAIDA = f"{DADOS}/analitico"
PARAMETROS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "parametros", "simples_nacional.csv")

# ---------- Hipóteses do cálculo ----------
LIMITE_SIMPLES = 4_800_000
LIMITE_PRESUMIDO = 78_000_000
FATOR_R_MINIMO = 0.28

# Lucro presumido: percentual da receita usado como base do IRPJ e da CSLL
PRESUNCAO_IRPJ = {"Comércio": 0.08, "Indústria": 0.08, "Serviços": 0.32}
PRESUNCAO_CSLL = {"Comércio": 0.12, "Indústria": 0.12, "Serviços": 0.32}
ACRESCIMO_LC_224 = 0.10      # presunção 10% maior sobre a receita acima de R$ 5 mi por ano (LC 224/2025)
LIMITE_LC_224 = 5_000_000

IRPJ = 0.15
ADICIONAL_IRPJ = 0.10        # sobre o lucro acima de R$ 20 mil por mês
LIMITE_ADICIONAL = 240_000   # R$ 20 mil x 12 meses
CSLL = 0.09
PIS_COFINS_CUMULATIVO = 0.0365       # Lucro Presumido: PIS 0,65% + Cofins 3%
PIS_COFINS_NAO_CUMULATIVO = 0.0925   # Lucro Real: PIS 1,65% + Cofins 7,6%, com crédito das compras
INSS_PATRONAL = 0.20
ICMS = 0.18                  # alíquota interna de SP, sobre a receita menos o custo das mercadorias
ISS = 0.05                   # alíquota máxima do ISS, sobre a receita dos serviços


def por_setor(valores):
    """Monta uma expressão que devolve o valor do dicionário conforme o setor."""
    expr = None
    for setor, valor in valores.items():
        cond = F.col("macro_setor") == setor
        expr = F.when(cond, valor) if expr is None else expr.when(cond, valor)
    return expr


def codigo(coluna, digitos):
    """Código como texto com zeros à esquerda (ex.: 1 -> '01'), como no criar_carteira.py."""
    return F.lpad(F.col(coluna).cast("long").cast("string"), digitos, "0")


def gravar_csv_unico(df, destino):
    """O Spark grava CSV em pasta; aqui o resultado vira um arquivo só, para o Colab."""
    temporario = destino + "_tmp"
    df.coalesce(1).write.mode("overwrite").option("header", True).csv(temporario)
    parte = glob.glob(os.path.join(temporario, "part-*.csv"))[0]
    shutil.move(parte, destino)
    shutil.rmtree(temporario)


spark = (SparkSession.builder
         .appName("calculo-tributario")
         .master("local[*]")
         .config("spark.sql.shuffle.partitions", "8")
         .getOrCreate())
spark.sparkContext.setLogLevel("ERROR")

# ---------- 1. Leitura ----------
esquema_movimentacao = T.StructType([
    T.StructField("arquivo_origem", T.StringType()),
    T.StructField("id_lancamento", T.StringType()),
    T.StructField("cnpj_basico", T.StringType()),
    T.StructField("competencia", T.StringType()),
    T.StructField("macro_setor", T.StringType()),
    T.StructField("cnae_fiscal_principal", T.StringType()),
    T.StructField("regime_atual", T.StringType()),
    T.StructField("receita_bruta_mensal", T.DoubleType()),
    T.StructField("folha_salarios_mensal", T.DoubleType()),
    T.StructField("custo_mercadoria_vendida", T.DoubleType()),
    T.StructField("despesas_operacionais", T.DoubleType()),
    T.StructField("compras_com_credito", T.DoubleType()),
    T.StructField("data_hora_geracao", T.StringType()),
    T.StructField("folha_imputada", T.BooleanType()),
    T.StructField("custo_imputado", T.BooleanType()),
    T.StructField("despesas_imputadas", T.BooleanType()),
])
movimentacao = spark.read.csv(f"{DADOS}/tratados/movimentacao_tratada.csv",
                              header=True, schema=esquema_movimentacao)

# No recorte os códigos podem vir como número (ex.: porte 1 em vez de "01")
recorte = (spark.read.parquet(f"{DADOS}/cnpj_sp_recorte_tributario_spark.parquet")
           .withColumn("cnpj_basico", codigo("cnpj_basico", 8))
           .withColumn("cnae_fiscal_principal", codigo("cnae_fiscal_principal", 7))
           .withColumn("porte_empresa", F.coalesce(codigo("porte_empresa", 2), F.lit("00"))))
parametros = spark.read.csv(PARAMETROS, header=True, inferSchema=True)

print(f"Lançamentos tratados: {movimentacao.count():,}")
print(f"Empresas no recorte da Receita: {recorte.count():,}")

# ---------- 2. Modelo estrela ----------
# Dimensão empresa: cadastro real da Receita, só das empresas que têm movimentação
dim_empresa = (recorte
               .join(movimentacao.select("cnpj_basico").distinct(), "cnpj_basico", "left_semi")
               .dropDuplicates(["cnpj_basico"])
               .select(
                   "cnpj_basico",
                   "cnae_fiscal_principal",
                   "macro_setor",
                   "porte_empresa",
                   F.when(F.col("porte_empresa") == "01", "Microempresa")
                    .when(F.col("porte_empresa") == "03", "Pequeno porte")
                    .when(F.col("porte_empresa") == "05", "Demais")
                    .otherwise("Não informado").alias("porte_desc"),
                   F.col("capital_social").cast("double").alias("capital_social"),
                   F.col("idade_anos").cast("double").alias("idade_anos"),
                   (F.col("enquadramento") == "Simples Nacional").alias("optante_simples")))

# Dimensão tempo: uma linha por competência
dim_tempo = (movimentacao.select("competencia").distinct()
             .withColumn("ano", F.substring("competencia", 1, 4).cast("int"))
             .withColumn("mes", F.substring("competencia", 6, 2).cast("int"))
             .withColumn("trimestre", F.ceil(F.col("mes") / 3).cast("int")))

# Fato: um lançamento por empresa e competência
fato_movimentacao = movimentacao.select(
    "id_lancamento", "cnpj_basico", "competencia", "regime_atual",
    "receita_bruta_mensal", "folha_salarios_mensal", "custo_mercadoria_vendida",
    "despesas_operacionais", "compras_com_credito",
    "folha_imputada", "custo_imputado", "despesas_imputadas")

# ---------- 3. Visão anual por empresa ----------
# Empresas com algum mês descartado na limpeza têm a soma anualizada (x 12 / meses)
anual = (fato_movimentacao.groupBy("cnpj_basico")
         .agg(F.countDistinct("competencia").alias("meses"),
              F.first("regime_atual").alias("regime_atual"),
              F.sum("receita_bruta_mensal").alias("receita"),
              F.sum("folha_salarios_mensal").alias("folha"),
              F.sum("custo_mercadoria_vendida").alias("custo"),
              F.sum("despesas_operacionais").alias("despesas"),
              F.sum("compras_com_credito").alias("compras"))
         .select("cnpj_basico", "meses", "regime_atual",
                 *[(F.col(c) * 12 / F.col("meses")).alias(f"{c}_12m")
                   for c in ["receita", "folha", "custo", "despesas", "compras"]])
         .withColumnRenamed("receita_12m", "rbt12")
         .join(dim_empresa.select("cnpj_basico", "macro_setor"), "cnpj_basico")
         .withColumn("fator_r", F.col("folha_12m") / F.col("rbt12"))
         .withColumn("margem", (F.col("rbt12") - F.col("custo_12m") - F.col("despesas_12m")
                                - F.col("folha_12m")) / F.col("rbt12")))

# ---------- 4. Simples Nacional ----------
anual = anual.withColumn(
    "anexo_simples",
    F.when(F.col("macro_setor") == "Comércio", "I")
     .when(F.col("macro_setor") == "Indústria", "II")
     .when(F.col("fator_r") >= FATOR_R_MINIMO, "III")
     .otherwise("V"))

faixas = F.broadcast(parametros.withColumnRenamed("anexo", "anexo_simples"))
anual = (anual.join(faixas,
                    (anual.anexo_simples == faixas.anexo_simples)
                    & (anual.rbt12 > faixas.receita_de)
                    & (anual.rbt12 <= faixas.receita_ate),
                    "left")
         .drop(faixas.anexo_simples, "receita_de", "receita_ate")
         .withColumnRenamed("faixa", "faixa_simples")
         .withColumn("imposto_simples",
                     F.when(F.col("rbt12") <= LIMITE_SIMPLES,
                            F.col("rbt12") * F.col("aliquota_nominal") - F.col("parcela_deduzir")))
         .drop("aliquota_nominal", "parcela_deduzir"))

# ---------- 5. Tributos comuns ao Presumido e ao Real ----------
anual = (anual
         .withColumn("inss_patronal", F.col("folha_12m") * INSS_PATRONAL)
         .withColumn("icms_iss",
                     F.when(F.col("macro_setor") == "Serviços", F.col("rbt12") * ISS)
                      .otherwise(F.greatest(F.col("rbt12") - F.col("custo_12m"), F.lit(0)) * ICMS)))

# ---------- 6. Lucro Presumido ----------
receita_ajustada = (F.least(F.col("rbt12"), F.lit(LIMITE_LC_224))
                    + F.greatest(F.col("rbt12") - LIMITE_LC_224, F.lit(0)) * (1 + ACRESCIMO_LC_224))
anual = (anual
         .withColumn("base_irpj_presumido", receita_ajustada * por_setor(PRESUNCAO_IRPJ))
         .withColumn("base_csll_presumido", receita_ajustada * por_setor(PRESUNCAO_CSLL))
         .withColumn("imposto_presumido", F.when(
             F.col("rbt12") <= LIMITE_PRESUMIDO,
             F.col("base_irpj_presumido") * IRPJ
             + F.greatest(F.col("base_irpj_presumido") - LIMITE_ADICIONAL, F.lit(0)) * ADICIONAL_IRPJ
             + F.col("base_csll_presumido") * CSLL
             + F.col("rbt12") * PIS_COFINS_CUMULATIVO
             + F.col("inss_patronal")
             + F.col("icms_iss")))
         .drop("base_irpj_presumido", "base_csll_presumido"))

# ---------- 7. Lucro Real ----------
anual = (anual
         .withColumn("pis_cofins_real",
                     F.greatest((F.col("rbt12") - F.col("compras_12m")) * PIS_COFINS_NAO_CUMULATIVO,
                                F.lit(0)))
         .withColumn("lucro_real",
                     F.col("rbt12") - F.col("custo_12m") - F.col("despesas_12m") - F.col("folha_12m")
                     - F.col("inss_patronal") - F.col("icms_iss") - F.col("pis_cofins_real"))
         .withColumn("imposto_real",
                     F.col("pis_cofins_real") + F.col("inss_patronal") + F.col("icms_iss")
                     + F.greatest(F.col("lucro_real"), F.lit(0)) * (IRPJ + CSLL)
                     + F.greatest(F.col("lucro_real") - LIMITE_ADICIONAL, F.lit(0)) * ADICIONAL_IRPJ)
         .drop("pis_cofins_real", "inss_patronal", "icms_iss"))

# ---------- 8. Comparação ----------
menor = F.least("imposto_simples", "imposto_presumido", "imposto_real")   # ignora regimes vazios
anual = (anual
         .withColumn("menor_imposto", menor)
         .withColumn("regime_mais_barato",
                     F.when(F.col("imposto_simples") == F.col("menor_imposto"), "Simples Nacional")
                      .when(F.col("imposto_presumido") == F.col("menor_imposto"), "Lucro Presumido")
                      .otherwise("Lucro Real"))
         .withColumn("imposto_regime_atual",
                     F.when(F.col("regime_atual") == "Simples Nacional", F.col("imposto_simples"))
                      .when(F.col("regime_atual") == "Lucro Presumido", F.col("imposto_presumido"))
                      .otherwise(F.col("imposto_real")))
         .withColumn("economia_estimada", F.col("imposto_regime_atual") - F.col("menor_imposto"))
         .withColumn("carga_atual", F.col("imposto_regime_atual") / F.col("rbt12"))
         .withColumn("carga_minima", F.col("menor_imposto") / F.col("rbt12"))
         .drop("macro_setor"))

reais = ["rbt12", "folha_12m", "custo_12m", "despesas_12m", "compras_12m", "lucro_real",
         "imposto_simples", "imposto_presumido", "imposto_real", "menor_imposto",
         "imposto_regime_atual", "economia_estimada"]
proporcoes = ["fator_r", "margem", "carga_atual", "carga_minima"]

simulacao = (dim_empresa.join(anual, "cnpj_basico")
             .select("cnpj_basico", "cnae_fiscal_principal", "macro_setor", "porte_empresa",
                     "porte_desc", "capital_social", "idade_anos", "optante_simples",
                     "regime_atual", "meses",
                     *[F.round(c, 2).cast("decimal(18,2)").alias(c) for c in reais],
                     *[F.round(c, 4).cast("decimal(10,4)").alias(c) for c in proporcoes],
                     "anexo_simples", "faixa_simples", "regime_mais_barato")
             .orderBy("cnpj_basico"))

# ---------- 9. Gravação ----------
os.makedirs(SAIDA, exist_ok=True)
dim_empresa.write.mode("overwrite").parquet(f"{SAIDA}/dim_empresa")
dim_tempo.write.mode("overwrite").parquet(f"{SAIDA}/dim_tempo")
fato_movimentacao.write.mode("overwrite").parquet(f"{SAIDA}/fato_movimentacao")
simulacao.write.mode("overwrite").parquet(f"{SAIDA}/simulacao_tributaria")
gravar_csv_unico(simulacao, f"{SAIDA}/simulacao_tributaria.csv")
print(f"Empresas simuladas: {simulacao.count():,}")

# ---------- 10. Resumo com Spark SQL ----------
simulacao.createOrReplaceTempView("simulacao")

print("\n== Regime atual x regime mais barato (empresas) ==")
spark.sql("""
    SELECT regime_atual,
           SUM(CASE WHEN regime_mais_barato = 'Simples Nacional' THEN 1 ELSE 0 END) AS simples,
           SUM(CASE WHEN regime_mais_barato = 'Lucro Presumido'  THEN 1 ELSE 0 END) AS presumido,
           SUM(CASE WHEN regime_mais_barato = 'Lucro Real'       THEN 1 ELSE 0 END) AS real,
           COUNT(*)                                                                 AS empresas
    FROM simulacao
    GROUP BY regime_atual
    ORDER BY regime_atual
""").show(truncate=False)

print("== Empresas que pagariam menos em outro regime, por setor ==")
spark.sql("""
    SELECT macro_setor,
           COUNT(*)                                                       AS empresas,
           SUM(CASE WHEN regime_mais_barato <> regime_atual THEN 1 ELSE 0 END) AS podem_economizar,
           ROUND(SUM(economia_estimada), 0)                               AS economia_total_ano
    FROM simulacao
    GROUP BY macro_setor
    ORDER BY economia_total_ano DESC
""").show(truncate=False)

print(f"Tabelas gravadas em {SAIDA}: dim_empresa, dim_tempo, fato_movimentacao, "
      "simulacao_tributaria (Parquet) e simulacao_tributaria.csv")
spark.stop()