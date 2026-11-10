from pyspark.sql import SparkSession, functions as F

spark = (SparkSession.builder
         .appName("limpeza")
         .master("local[*]")
         .getOrCreate())
spark.sparkContext.setLogLevel("ERROR")

esquema = """
    id_lancamento STRING, cnpj_basico STRING, competencia STRING,
    macro_setor STRING, cnae_fiscal_principal STRING, regime_atual STRING,
    receita_bruta_mensal DOUBLE, folha_salarios_mensal DOUBLE,
    custo_mercadoria_vendida DOUBLE, despesas_operacionais DOUBLE,
    compras_com_credito DOUBLE, data_hora_geracao STRING
"""
df = spark.read.csv("/dados/exemplo_dados.csv", header=True, schema=esquema)
n0 = df.count()

# 1. Duplicatas: uma linha por empresa e competência
df1 = df.dropDuplicates(["cnpj_basico", "competencia"])
n1 = df1.count()

# 2. Receita impossível (zero ou negativa)
df2 = df1.filter(F.col("receita_bruta_mensal") > 0)
n2 = df2.count()

# 3. Discrepantes pelo IQR: marcamos antes de remover
q1, q3 = df2.approxQuantile("receita_bruta_mensal", [0.25, 0.75], 0.01)
limite = q3 + 3 * (q3 - q1)
df3 = df2.withColumn("outlier_receita", F.col("receita_bruta_mensal") > limite)

print(f"Q1 = {q1:,.2f} | Q3 = {q3:,.2f} | limite superior = {limite:,.2f}")
print("\n== Linhas problemáticas ==")
(df.filter((F.col("receita_bruta_mensal") <= 0) | (F.col("receita_bruta_mensal") > limite))
   .select("cnpj_basico", "competencia", "macro_setor", "receita_bruta_mensal")
   .show())

df_limpo = df3.filter(~F.col("outlier_receita")).drop("outlier_receita")
n3 = df_limpo.count()

print("== Funil de limpeza ==")
print(f"Original:                 {n0}")
print(f"Sem duplicatas:           {n1}  (-{n0 - n1})")
print(f"Sem receita inválida:     {n2}  (-{n1 - n2})")
print(f"Sem discrepantes (IQR):   {n3}  (-{n2 - n3})")

print("\n== Receita depois da limpeza ==")
df_limpo.select("receita_bruta_mensal").describe().show()
mediana = df_limpo.approxQuantile("receita_bruta_mensal", [0.5], 0.01)[0]
print(f"Mediana: {mediana:,.2f}")

print("\n== Receita média por setor ==")
(df_limpo.groupBy("macro_setor")
         .agg(F.count("*").alias("lancamentos"),
              F.round(F.avg("receita_bruta_mensal"), 2).alias("receita_media"))
         .orderBy(F.desc("receita_media"))
         .show())

spark.stop()