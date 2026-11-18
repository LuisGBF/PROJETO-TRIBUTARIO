# Pipeline Tributário

**Automação e Escalabilidade de Pipelines de Big Data e Análise de Dados**
*Diagnóstico Automatizado de Enquadramento Tributário para Consultoria Contábil*

Pipeline que compara a carga tributária estimada de empresas nos regimes Simples Nacional, Lucro Presumido e Lucro Real. O repositório reúne a infraestrutura como código (VMs e Docker), o simulador de movimentação financeira, o tratamento e a análise exploratória em R, o monitoramento com Prometheus e Grafana e a análise da base pública de CNPJ com Apache Spark.

| Etapa | Ferramenta | Função |
|---|---|---|
| Provisionamento | OpenTofu + libvirt/KVM | Cria as VMs Ubuntu 24.04 (geradora e monitoramento) e gera o inventário do Ansible |
| Configuração inicial | cloud-init | Usuário, acesso SSH por chave e hostname |
| Preparação do ambiente | Ansible | Instala o Docker, o node_exporter, o Prometheus e o Grafana |
| Implantação | SCP + Docker | Transfere o simulador e a carteira para a VM e constrói a imagem |
| Dados cadastrais | Dados Abertos do CNPJ (Receita Federal) | Base real de empresas, competência 2026-09-14 |
| Recorte da base do CNPJ | Python (pandas) no Google Colab | Filtra as empresas e gera o arquivo Parquet |
| Carteira de empresas | `simulador/criar_carteira.py` | Sorteia 1.000 empresas reais do recorte para o simulador |
| Geração de dados financeiros | Simulador em Python (contêiner na VM geradora) | Produz os lançamentos mensais da carteira em CSV |
| Coleta | rsync | Copia os CSVs brutos da VM para `dados/brutos` |
| Diagnóstico, limpeza e exploração | R (tidyverse) | Trata os dados brutos e gera `dados/tratados` e os gráficos |
| Integração | `pipeline.sh` | Executa as etapas em sequência, com registro de execução e parada em caso de falha |
| Monitoramento | node_exporter + Prometheus + Grafana | Acompanha CPU, memória, disco e disponibilidade da VM geradora |
| Processamento | Apache Spark (PySpark, contêiner) | DataFrames, agrupamentos e Spark SQL sobre a base do CNPJ |

## Fluxo do pipeline

```
VM geradora (simulador em Docker)
   │  um CSV por competência, em /var/lib/simulador/dados
   ▼
rsync  ──►  dados/brutos            (dados brutos, nunca alterados)
   ▼
aed/diagnostico.R                   (contagem dos problemas de qualidade)
aed/limpeza.R  ──►  dados/tratados  (dados tratados + registros descartados com o motivo)
aed/exploracao.R  ──►  aed/graficos (medidas, agrupamentos e gráficos)

VM de monitoramento: Prometheus coleta as métricas da VM geradora a cada 15 s; Grafana exibe o painel
```

O `pipeline.sh` executa as etapas de geração, coleta e tratamento com um único comando e grava um log de cada execução em `logs/`.

## Estrutura

```
infraestrutura/
├── main.tf, variables.tf     # provisionamento da VM geradora e inventário do Ansible
├── monitoramento.tf          # provisionamento da VM de monitoramento
├── cloud_init.cfg            # configuração do primeiro boot
├── implantar.sh              # envia o simulador e a carteira por SCP e constrói a imagem na VM
├── ansible/
│   ├── inventory.ini         # gerado automaticamente pelo OpenTofu
│   ├── playbook.yml          # Docker e diretórios da VM geradora
│   └── monitoramento.yml     # node_exporter na geradora; Docker, Prometheus e Grafana no monitoramento
└── monitoramento/
    └── painel_vm_geradora.json  # painel do Grafana
simulador/
├── Dockerfile
├── simulador.py              # gerador de dados
├── criar_carteira.py         # sorteia a carteira de empresas reais a partir do recorte do CNPJ
├── carteira_empresas.csv     # carteira fixa usada pelo simulador
└── requirements.txt
aed/
├── diagnostico.R             # diagnóstico da qualidade dos dados brutos
├── limpeza.R                 # limpeza, tratamento e verificações de qualidade
├── exploracao.R              # análise exploratória dos dados tratados
└── graficos/                 # gráficos gerados pela exploração
spark/
├── Dockerfile                # Python + Java + PySpark
├── requirements.txt
├── converter.py              # ajusta timestamps do Parquet para o Spark
├── analise.py                # análise principal (DataFrames e Spark SQL)
├── limpeza.py                # exemplo de tratamento com Spark
├── diagnostico.py            # exemplo de verificação de qualidade com Spark
└── resultados_analise.txt    # saída registrada da análise
notebooks/
└── pipeline_tributario.ipynb # recorte da base do CNPJ (a adicionar ao repositório)
dados/
└── exemplo_dados.csv         # exemplo gerado pelo simulador
pipeline.sh                   # integração das etapas, com log de execução
docker-compose.yml            # serviços: simulador, visualizador, spark
```

## Dados

Os dados não são versionados: o `.gitignore` bloqueia tudo em `dados/`, exceto o exemplo, e os logs em `logs/`.

- **Fonte:** Dados Abertos do CNPJ (Receita Federal), competência 2026-09-14.
- **Recorte:** empresas ativas, matrizes, sediadas em São Paulo, entidades empresariais não-MEI (1.513.185 empresas).
- **Como gerar:** execute o notebook do recorte no Google Colab. Ele baixa os arquivos da Receita, trata os dados e salva `cnpj_sp_recorte_tributario.parquet`.
- **Carteira:** `simulador/carteira_empresas.csv` guarda 1.000 empresas reais de Comércio, Serviços e Indústria sorteadas do recorte, com CNPJ básico, CNAE, porte e opção pelo Simples. É versionada, então o pipeline não depende do Colab para rodar.
- **Valores financeiros:** a base pública não traz receita, folha nem custos. O simulador gera esses valores de forma fictícia para as empresas da carteira, ligadas à base por `cnpj_basico`. Resultados que usam esses campos são demonstração do método, e não diagnóstico de empresas reais.

## Pré-requisitos

Máquina hospedeira Linux com virtualização ativada na BIOS (testado em Ubuntu 26.04).

**Virtualização e infraestrutura:**

```bash
sudo apt install -y qemu-kvm libvirt-daemon-system libvirt-clients virtinst genisoimage ansible rsync
sudo adduser "$USER" libvirt && sudo adduser "$USER" kvm   # depois, encerre a sessão e entre de novo
sudo virsh net-autostart default && sudo virsh net-start default

curl --proto '=https' --tlsv1.2 -fsSL https://get.opentofu.org/install-opentofu.sh -o install-opentofu.sh
chmod +x install-opentofu.sh && ./install-opentofu.sh --install-method standalone --skip-verify
rm -f install-opentofu.sh
```

**R e pacotes da análise exploratória:**

```bash
sudo apt install -y --no-install-recommends r-base r-cran-tidyverse r-cran-skimr
```

O pacote `janitor` não está no apt. Instale pelo console do R (ou do RStudio) com `install.packages("janitor")`.

Nenhuma credencial é versionada. Gere uma chave SSH e baixe a imagem do Ubuntu:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/vm_pipeline -N ""
mkdir -p ~/imagens-vm
wget -P ~/imagens-vm https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
```

Caminhos diferentes podem ser informados com `-var`, conforme `infraestrutura/variables.tf`.

## Montagem do ambiente

```bash
cd infraestrutura

# 1. Provisionar as duas VMs (geradora e monitoramento)
tofu init
tofu apply

# 2. Verificar o cloud-init (aguarde cerca de um minuto)
ssh -i ~/.ssh/vm_pipeline pipeline@$(tofu output -raw ip_vm)
cloud-init status                       # status: done
exit

# 3. Preparar a VM geradora (instala o Docker)
ansible-playbook -i ansible/inventory.ini ansible/playbook.yml

# 4. Transferir o simulador e a carteira e construir a imagem na VM
./implantar.sh

# 5. Instalar o monitoramento (node_exporter, Prometheus e Grafana)
ansible-playbook -i ansible/inventory.ini ansible/monitoramento.yml
```

Os playbooks são idempotentes: uma segunda execução termina com `changed=0`.

## Execução do pipeline

Na raiz do projeto, com as VMs ligadas:

```bash
# Gera as competências na VM, copia os brutos e roda o tratamento em R
./pipeline.sh 2025-11 2025-12 2026-01 2026-02 2026-03 2026-04 2026-05 2026-06 2026-07 2026-08 2026-09 2026-10

# Sem competências: só copia os arquivos novos da VM e roda o tratamento
./pipeline.sh
```

| Etapa | Comando executado | Resultado |
|---|---|---|
| 1. Geração | `docker run ... simulador-tributario --competencia AAAA-MM` na VM | Um CSV por competência em `/var/lib/simulador/dados` |
| 2. Coleta | `rsync` pela conexão SSH | CSVs novos em `dados/brutos` |
| 3. Diagnóstico | `Rscript aed/diagnostico.R` | Contagem de duplicatas, ausentes, formatos, categorias, CNPJs e discrepantes |
| 4. Limpeza | `Rscript aed/limpeza.R` | `dados/tratados/movimentacao_tratada.csv` e `registros_descartados.csv` |
| 5. Exploração | `Rscript aed/exploracao.R` | Tabelas e gráficos em `aed/graficos` |

**Registros de execução:** tudo o que aparece na tela é gravado em `logs/pipeline_AAAAMMDD_HHMMSS.log`.

**Identificação de falhas:** o script para no primeiro erro e escreve `FALHA` com a etapa em que parou. A limpeza também interrompe o pipeline quando os dados tratados não passam nas verificações de qualidade (sem duplicatas, um registro por empresa e mês, CNPJ com 8 dígitos, setor padronizado, sem valores ausentes e receita positiva), antes de gravar o CSV.

**Reprocessamento:** a mesma empresa na mesma competência sempre recebe o mesmo `id_lancamento`. Gerar um mês de novo não duplica dados, porque a limpeza remove os registros repetidos.

## Tratamento em R

| Script | O que faz |
|---|---|
| `diagnostico.R` | Lê os brutos como texto e conta cada tipo de problema de qualidade |
| `limpeza.R` | Remove duplicatas; padroniza CNPJ, setor, números e datas; separa receitas negativas e infladas (gastos abaixo de 1% da receita) com o motivo; preenche ausentes pela proporção da própria empresa nos outros meses (ou do setor); verifica a qualidade antes de gravar |
| `exploracao.R` | Medidas descritivas, frequências, agrupamentos, correlação de Spearman, receita dos últimos 12 meses (RBT12), Fator R, porte real da carteira e gráficos |

Os scripts também podem ser abertos no RStudio pelo projeto `PROJETO-TRIBUTARIO.Rproj`.

## Monitoramento

A VM de monitoramento roda o Prometheus e o Grafana em contêineres. O node_exporter, instalado na VM geradora, expõe as métricas na porta 9100, e o Prometheus as coleta a cada 15 segundos.

```bash
cd infraestrutura
tofu output url_grafana     # endereço do Grafana (porta 3000)
```

O Grafana já sobe com o Prometheus cadastrado e com o painel **VM geradora - recursos** (CPU, memória, disco e indicador "No ar" / "Fora do ar"). O primeiro acesso usa o usuário `admin` e a senha `admin`. Os alvos do Prometheus podem ser conferidos em `http://IP_DO_MONITORAMENTO:9090/targets`.

## Simulador

Gera os lançamentos mensais de uma **carteira fixa de empresas reais**, sorteadas do recorte da base do CNPJ. O cadastro é real (CNPJ, CNAE, setor, porte e opção pelo Simples); receita, folha, custos e despesas são fictícios.

| Grupo | Campos |
|---|---|
| Identificação | `id_lancamento`, `cnpj_basico` |
| Classificação | `macro_setor`, `cnae_fiscal_principal`, `regime_atual` |
| Valores do mês | `receita_bruta_mensal`, `folha_salarios_mensal`, `custo_mercadoria_vendida`, `despesas_operacionais`, `compras_com_credito` |
| Temporal | `competencia`, `data_hora_geracao` |

Como os valores são gerados:

- **Mesma empresa todo mês:** cada empresa tem um perfil estável (receita anual, estrutura de custos e regime), calculado a partir do próprio CNPJ. Assim é possível somar os últimos 12 meses (RBT12) e calcular o Fator R.
- **Receita coerente com o cadastro:** a receita anual respeita o porte declarado (microempresa até R$ 360 mil, pequeno porte até R$ 4,8 milhões) e o teto do Simples para as optantes.
- **Regime:** optantes do Simples ficam no Simples Nacional. A base pública não separa Lucro Presumido de Lucro Real, então 20% das demais empresas são sorteadas para o Lucro Real (todas acima de R$ 78 milhões por ano).
- **Variação mensal:** a receita varia de um mês para o outro e tem sazonalidade no Comércio (pico em novembro e dezembro).

Parâmetros: `--carteira` (padrão `carteira_empresas.csv`), `--registros` (usa só as N primeiras empresas; padrão: todas), `--saida`, `--competencia` (AAAA-MM), `--semente` (sorteio dos defeitos) e `--taxa-defeitos` (padrão 0,10). Uma parcela dos registros recebe problemas de qualidade controlados (valores ausentes, formatos divergentes, categorias inconsistentes, CNPJ fora do padrão, discrepantes e duplicatas), tratados no R. Use `--taxa-defeitos 0` para gerar dados limpos.

### Carteira de empresas

A carteira é criada uma vez a partir do Parquet do recorte e fica versionada. Requer `pandas` e `pyarrow`:

```bash
python simulador/criar_carteira.py dados/cnpj_sp_recorte_tributario.parquet --saida simulador/carteira_empresas.csv
```

Por padrão são sorteadas 1.000 empresas, com semente fixa (`--tamanho` e `--semente` mudam isso).

## Execução com Docker (local)

Pré-requisito: Docker com o plugin Compose.

```bash
# Gerar dados do simulador em dados/
docker compose run --rm simulador --registros 50

# Análise com Spark sobre a base do CNPJ
# 1. Coloque cnpj_sp_recorte_tributario.parquet em dados/
# 2. Converta os timestamps (o pandas grava nanossegundos; o Spark 3.5 lê microssegundos)
docker compose build spark
docker compose run --rm --user "$(id -u):$(id -g)" spark python converter.py
# 3. Execute a análise
docker compose run --rm spark python analise.py
```

O `analise.py` carrega o Parquet, cria colunas derivadas, aplica filtros e agrupamentos com DataFrames, executa consultas Spark SQL e imprime o plano de execução e o tempo com 1 e 8 partições. A saída de uma execução está em `spark/resultados_analise.txt`.

O tratamento oficial dos dados do simulador é feito em R. Os scripts abaixo são exemplos de Spark e usam `dados/exemplo_dados.csv`:

```bash
docker compose run --rm spark python diagnostico.py   # nulos, categorias, duplicatas, estatísticas
docker compose run --rm spark python limpeza.py       # remove duplicatas, receita inválida e discrepantes (IQR)
```

## Reconstrução

```bash
cd infraestrutura
tofu destroy
tofu apply
ssh-keygen -R "$(tofu output -raw ip_vm)"              # remove as chaves de host das VMs anteriores
ssh-keygen -R "$(tofu output -raw ip_monitoramento)"
ansible-playbook -i ansible/inventory.ini ansible/playbook.yml
./implantar.sh
ansible-playbook -i ansible/inventory.ini ansible/monitoramento.yml
```

## Solução de problemas

**`Permission denied` em arquivo `.qcow2` no `tofu apply`:** o AppArmor bloqueia o disco da VM. Aceitável apenas em laboratório local:

```bash
echo 'security_driver = "none"' | sudo tee -a /etc/libvirt/qemu.conf
sudo systemctl restart libvirtd
```

**`qemu-kvm` não encontrado:** em versões recentes do Ubuntu, use `qemu-system-x86`.

**Ansible `UNREACHABLE` ou `Could not get lock` após o `apply`:** o cloud-init ainda está em execução. Aguarde e tente novamente.

**VMs desligadas após reiniciar o computador:** `virsh -c qemu:///system start vm-treino` e `virsh -c qemu:///system start vm-monitoramento`.

**VM recebeu outro IP:** execute `tofu plan` para confirmar que apenas o inventário será alterado e, em seguida, `tofu apply`. Depois rode de novo o `monitoramento.yml`, para o Prometheus apontar para o IP novo.

**`FALHA` no `pipeline.sh`:** abra o log mais recente em `logs/` e veja a última etapa anunciada antes da falha. Na etapa 1 ou 2, confira se a VM geradora está ligada; na etapa 4, veja qual verificação de qualidade deu `FALSE`.

**Spark: `Illegal Parquet type: INT64 (TIMESTAMP(NANOS,false))`:** o Parquet foi gravado pelo pandas com datas em nanossegundos. Execute `converter.py` e leia o arquivo `_spark.parquet`.

## Equipe

- Betânia Amâncio Pereira
- Gabriel Meneghetti Zanardo
- Giovana Muniz dos Santos
- Luis Gabriel Brito Felicio
- Luis Fernando Menezes Ferreira Leite
- Virgilio
