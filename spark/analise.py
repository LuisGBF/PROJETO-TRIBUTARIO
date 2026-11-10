import time
from pyspark.sql import SparkSession, functions as F

spark = (SparkSession.builder
         .appName("analise-tributaria")
         .master("local[*]")
         .config("spark.sql.shuffle.partitions", "8")  # padrão é 200, exagero p/ 1,5 mi de linhas
         .getOrCreate())
spark.sparkContext.setLogLevel("ERROR")

# ---------- 1. Carregamento ----------
df = spark.read.parquet("/dados/cnpj_sp_recorte_tributario_spark.parquet")
df.cache()
total = df.count()
print(f"Empresas: {total:,} | Partições: {df.rdd.getNumPartitions()} | "
      f"Núcleos (paralelismo): {spark.sparkContext.defaultParallelism}")

# ---------- 2. Transformações e filtros (DataFrames) ----------
df = (df
      .withColumn("porte_desc",
                  F.when(F.col("porte_empresa") == "01", "Microempresa")
                   .when(F.col("porte_empresa") == "03", "Pequeno porte")
                   .when(F.col("porte_empresa") == "05", "Demais")
                   .otherwise("Não informado"))
      .withColumn("faixa_idade",
                  F.when(F.col("idade_anos") < 1, "1) menos de 1 ano")
                   .when(F.col("idade_anos") < 3, "2) 1 a 3 anos")
                   .when(F.col("idade_anos") < 5, "3) 3 a 5 anos")
                   .when(F.col("idade_anos") < 10, "4) 5 a 10 anos")
                   .when(F.col("idade_anos") < 20, "5) 10 a 20 anos")
                   .otherwise("6) 20 anos ou mais"))
      .withColumn("fora_simples", (F.col("enquadramento") == "Lucro Presumido ou Real").cast("int")))

print("\n== Filtro: Presumido/Real com capital acima de R$ 1 milhão ==")
grandes = (df.filter((F.col("fora_simples") == 1) & (F.col("capital_social") > 1_000_000))
             .select("cnpj_basico", "macro_setor", "capital_social", "idade_anos"))
print("Quantidade:", grandes.count())
grandes.orderBy(F.desc("capital_social")).show(5)

# ---------- 3. Agrupamentos ----------
print("== Enquadramento ==")
(df.groupBy("enquadramento").count()
   .withColumn("pct", F.round(F.col("count") / total * 100, 1))
   .show())

print("== % fora do Simples por setor ==")
(df.groupBy("macro_setor")
   .agg(F.count("*").alias("empresas"),
        F.round(F.avg("fora_simples") * 100, 1).alias("pct_fora_simples"))
   .orderBy(F.desc("pct_fora_simples"))
   .show())

print("== Capital social: média x mediana por enquadramento ==")
(df.groupBy("enquadramento")
   .agg(F.round(F.avg("capital_social"), 0).alias("media"),
        F.percentile_approx("capital_social", 0.5).alias("mediana"))
   .show())

print("== % fora do Simples por faixa de idade ==")
(df.groupBy("faixa_idade")
   .agg(F.count("*").alias("empresas"),
        F.round(F.avg("fora_simples") * 100, 1).alias("pct_fora_simples"))
   .orderBy("faixa_idade")
   .show())

print("== Top 10 atividades (CNAE) ==")
(df.groupBy("cnae_fiscal_principal")
   .agg(F.count("*").alias("empresas"),
        F.round(F.avg("fora_simples") * 100, 1).alias("pct_fora_simples"))
   .orderBy(F.desc("empresas"))
   .show(10))

# ---------- 4. Spark SQL ----------
df.createOrReplaceTempView("empresas")

print("== SQL: setor x porte ==")
spark.sql("""
    SELECT macro_setor,
           porte_desc,
           COUNT(*)                                   AS empresas,
           ROUND(AVG(fora_simples) * 100, 1)          AS pct_fora_simples,
           PERCENTILE_APPROX(capital_social, 0.5)     AS capital_mediano
    FROM empresas
    GROUP BY macro_setor, porte_desc
    HAVING COUNT(*) > 1000
    ORDER BY empresas DESC
""").show(15, truncate=False)

print("== SQL: ranking de setores com CTE ==")
spark.sql("""
    WITH por_setor AS (
        SELECT macro_setor,
               COUNT(*)           AS empresas,
               SUM(fora_simples)  AS fora_simples
        FROM empresas
        GROUP BY macro_setor
    )
    SELECT macro_setor, empresas, fora_simples,
           ROUND(fora_simples / empresas * 100, 1) AS pct_fora_simples
    FROM por_setor
    ORDER BY pct_fora_simples DESC
""").show(truncate=False)

# ---------- 5. Evidência do processamento distribuído ----------
print("== Plano de execução do groupBy (procure por 'Exchange' = shuffle) ==")
df.groupBy("macro_setor", "enquadramento").count().explain()

for n in (1, 8):
    t0 = time.perf_counter()
    df.repartition(n).groupBy("cnae_fiscal_principal").count().count()
    print(f"Com {n} partição(ões): {time.perf_counter() - t0:.2f}s")

spark.stop()