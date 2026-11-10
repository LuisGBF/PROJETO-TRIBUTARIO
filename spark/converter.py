#Converte de nanosegundos para micro, ja que o spark 3.5 n entende nano
import pyarrow.parquet as pq

ORIGEM = "/dados/cnpj_sp_recorte_tributario.parquet"
DESTINO = "/dados/cnpj_sp_recorte_tributario_spark.parquet"

tabela = pq.read_table(ORIGEM)

# Regrava com datas em microssegundos, que o Spark entende
pq.write_table(tabela, DESTINO,
               coerce_timestamps="us",
               allow_truncated_timestamps=True)

print("Linhas:", tabela.num_rows)
print("Colunas:", tabela.num_columns)
print(tabela.schema)