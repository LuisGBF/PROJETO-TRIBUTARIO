#!/usr/bin/env bash
# Pipeline: gera os dados na VM, copia para o notebook, trata em R e calcula os tributos no Spark
# Uso: ./pipeline.sh 2025-11 2025-12 ...   (competências a gerar na VM)

set -e
cd "$(dirname "$0")"

mkdir -p logs dados/brutos
LOG="logs/pipeline_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1
trap 'echo "== FALHA: o pipeline parou na etapa acima ($(date "+%d/%m/%Y %H:%M:%S"))"' ERR

IP=$(tofu -chdir=infraestrutura output -raw ip_vm)
CHAVE="$HOME/.ssh/vm_pipeline"

echo "== $(date '+%d/%m/%Y %H:%M:%S') 1. Gerando os dados na VM"
for COMPETENCIA in "$@"; do
    ssh -i "$CHAVE" pipeline@"$IP" "docker run --rm -v /var/lib/simulador/dados:/dados simulador-tributario --competencia $COMPETENCIA"
done

echo "== $(date '+%d/%m/%Y %H:%M:%S') 2. Copiando os dados brutos da VM"
rsync -av --include='movimentacao_*.csv' --exclude='*' -e "ssh -i $CHAVE" pipeline@"$IP":/var/lib/simulador/dados/ dados/brutos/

echo "== $(date '+%d/%m/%Y %H:%M:%S') 3. Diagnóstico em R"
Rscript aed/diagnostico.R

echo "== $(date '+%d/%m/%Y %H:%M:%S') 4. Limpeza e tratamento em R"
Rscript aed/limpeza.R

echo "== $(date '+%d/%m/%Y %H:%M:%S') 5. Exploração em R"
Rscript aed/exploracao.R

echo "== $(date '+%d/%m/%Y %H:%M:%S') 6. Cálculo tributário no Spark"
if [ ! -f dados/cnpj_sp_recorte_tributario_spark.parquet ]; then
    docker compose run --rm -T spark python converter.py
fi
docker compose run --rm -T spark python calculo_tributario.py

echo "== $(date '+%d/%m/%Y %H:%M:%S') Pipeline concluído com sucesso"