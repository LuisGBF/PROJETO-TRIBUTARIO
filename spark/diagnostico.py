from pyspark.sql import SparkSession, functions as F

spark = (SparkSession.builder
         .appName("diagnostico")
         .master("local[*]")
         .getOrCreate())
spark.sparkContext.setLogLevel("ERROR")

# Schema explícito: cnpj_basico e cnae como texto (preserva zeros à esquerda)
esquema = """
    id_lancamento STRING, cnpj_basico STRING, competencia STRING,
    macro_setor STRING, cnae_fiscal_principal STRING, regime_atual STRING,
    receita_bruta_mensal DOUBLE, folha_salarios_mensal DOUBLE,
    custo_mercadoria_vendida DOUBLE, despesas_operacionais DOUBLE,
    compras_com_credito DOUBLE, data_hora_geracao STRING
"""
df = spark.read.csv("/dados/exemplo_dados.csv", header=True, schema=esquema)

print("== 1. Valores ausentes por coluna ==")
df.select([F.sum(F.col(c).isNull().cast("int")).alias(c) for c in df.columns]).show()

print("== 2. Categorias de regime_atual ==")
df.groupBy("regime_atual").count().orderBy(F.desc("count")).show()

print("== 3. Duplicatas ==")
total = df.count()
unicos = df.dropDuplicates(["cnpj_basico", "competencia"]).count()
print(f"Linhas: {total} | únicas por empresa+mês: {unicos} | duplicadas: {total - unicos}")

print("== 4. Resumo estatístico da receita ==")
df.select("receita_bruta_mensal").describe().show()

spark.stop()