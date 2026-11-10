# Pipeline Tributário

**Automação e Escalabilidade de Pipelines de Big Data e Análise de Dados**
*Diagnóstico Automatizado de Enquadramento Tributário para Consultoria Contábil*

Pipeline que compara a carga tributária estimada de empresas nos regimes Simples Nacional, Lucro Presumido e Lucro Real. O repositório reúne a infraestrutura como código (VM e Docker), o simulador de movimentação financeira, o tratamento da base pública de CNPJ e a análise com Apache Spark.

| Etapa | Ferramenta | Função |
|---|---|---|
| Provisionamento | OpenTofu + libvirt/KVM | Cria a VM Ubuntu 24.04 e gera o inventário do Ansible |
| Configuração inicial | cloud-init | Usuário, acesso SSH por chave e hostname |
| Preparação do ambiente | Ansible | Instala o Docker Engine e cria os diretórios na VM |
| Implantação | SCP + Docker | Transfere o simulador para a VM e constrói a imagem |
| Geração de dados financeiros | Simulador em Python (contêiner) | Produz os lançamentos mensais em CSV |
| Dados cadastrais | Dados Abertos do CNPJ (Receita Federal) | Base real de empresas, competência 2026-09-14 |
| Tratamento e análise exploratória | Python (pandas) no Google Colab | Recorte, limpeza e gráficos; gera o arquivo Parquet |
| Processamento | Apache Spark (PySpark, contêiner) | DataFrames, agrupamentos e Spark SQL |

## Estrutura

```
infraestrutura/
├── main.tf, variables.tf     # provisionamento da VM
├── cloud_init.cfg            # configuração do primeiro boot
├── implantar.sh              # envia o simulador por SCP e constrói a imagem na VM
└── ansible/
    ├── inventory.ini         # gerado automaticamente pelo OpenTofu
    └── playbook.yml          # instalação do Docker e diretórios
simulador/
├── Dockerfile
├── simulador.py              # gerador de dados
└── requirements.txt
spark/
├── Dockerfile                # Python + Java + PySpark
├── requirements.txt
├── converter.py              # ajusta timestamps do Parquet para o Spark
├── analise.py                # análise principal (DataFrames e Spark SQL)
├── limpeza.py                # tratamento dos dados do simulador
├── diagnostico.py            # verificação de qualidade dos dados do simulador
└── resultados_analise.txt    # saída registrada da análise
notebooks/
└── pipeline_tributario.ipynb # análise exploratória da base do CNPJ
dados/
└── exemplo_dados.csv         # exemplo gerado pelo simulador
docker-compose.yml            # serviços: simulador, visualizador, spark
```

## Dados

Os dados não são versionados: o `.gitignore` bloqueia tudo em `dados/`, exceto o exemplo.

- **Fonte:** Dados Abertos do CNPJ (Receita Federal), competência 2026-09-14.
- **Recorte:** empresas ativas, matrizes, sediadas em São Paulo, entidades empresariais não-MEI (1.513.185 empresas).
- **Como gerar:** execute `notebooks/pipeline_tributario.ipynb` no Google Colab. Ele baixa os arquivos da Receita, trata os dados e salva `cnpj_sp_recorte_tributario.parquet`.
- **Valores financeiros:** a base pública não traz receita, folha nem custos. O simulador gera esses valores de forma fictícia, ligados por `cnpj_basico` e CNAE. Resultados que usam esses campos são demonstração do método, e não diagnóstico de empresas reais.

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

Scripts do simulador, que usam `dados/exemplo_dados.csv`:

```bash
docker compose run --rm spark python diagnostico.py   # nulos, categorias, duplicatas, estatísticas
docker compose run --rm spark python limpeza.py       # remove duplicatas, receita inválida e discrepantes (IQR)
```

## Pré-requisitos da VM

Máquina hospedeira Linux com virtualização ativada na BIOS (testado em Ubuntu 26.04):

```bash
sudo apt install -y qemu-kvm libvirt-daemon-system libvirt-clients virtinst genisoimage ansible
sudo adduser "$USER" libvirt && sudo adduser "$USER" kvm   # depois, encerre a sessão e entre de novo
sudo virsh net-autostart default && sudo virsh net-start default

curl --proto '=https' --tlsv1.2 -fsSL https://get.opentofu.org/install-opentofu.sh -o install-opentofu.sh
chmod +x install-opentofu.sh && ./install-opentofu.sh --install-method standalone --skip-verify
rm -f install-opentofu.sh
```

Nenhuma credencial é versionada. Gere uma chave SSH e baixe a imagem do Ubuntu:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/vm_pipeline -N ""
mkdir -p ~/imagens-vm
wget -P ~/imagens-vm https://cloud-images.ubuntu.com/noble/current/noble-server-cloudimg-amd64.img
```

Caminhos diferentes podem ser informados com `-var`, conforme `infraestrutura/variables.tf`.

## Execução na VM

```bash
cd infraestrutura

# 1. Provisionar a VM
tofu init
tofu apply

# 2. Verificar o cloud-init (aguarde cerca de um minuto)
ssh -i ~/.ssh/vm_pipeline pipeline@$(tofu output -raw ip_vm)
cloud-init status                       # status: done
cat /var/log/cloud-init-pipeline.log    # data de aplicação
exit

# 3. Preparar o ambiente (instala o Docker)
ansible -i ansible/inventory.ini simulador -m ping
ansible-playbook -i ansible/inventory.ini ansible/playbook.yml

# 4. Transferir o simulador e construir a imagem na VM
./implantar.sh

# 5. Executar o simulador na VM
ssh -i ~/.ssh/vm_pipeline pipeline@$(tofu output -raw ip_vm)
docker run --rm -v /var/lib/simulador/dados:/dados simulador-tributario --registros 50
ls -l /var/lib/simulador/dados          # um arquivo novo por execução
```

O playbook é idempotente: uma segunda execução termina com `changed=0`. Os dados ficam em `/var/lib/simulador/dados` e cada execução do simulador gera um novo arquivo, sem sobrescrever os anteriores.

## Simulador

Gera lançamentos mensais de empresas fictícias com as variáveis necessárias ao cálculo tributário, ausentes da base pública da Receita Federal.

| Grupo | Campos |
|---|---|
| Identificação | `id_lancamento`, `cnpj_basico` |
| Classificação | `macro_setor`, `cnae_fiscal_principal`, `regime_atual` |
| Valores do mês | `receita_bruta_mensal`, `folha_salarios_mensal`, `custo_mercadoria_vendida`, `despesas_operacionais`, `compras_com_credito` |
| Temporal | `competencia`, `data_hora_geracao` |

Parâmetros: `--registros` (mínimo 10, padrão 50), `--saida`, `--competencia` (AAAA-MM), `--semente` e `--taxa-defeitos` (padrão 0,10). Uma parcela dos registros recebe problemas de qualidade controlados (valores ausentes, formatos divergentes, categorias inconsistentes, discrepantes e duplicatas), tratados nas etapas seguintes do pipeline. Use `--taxa-defeitos 0` para gerar dados limpos.

## Reconstrução

```bash
tofu destroy
tofu apply
ssh-keygen -R "$(tofu output -raw ip_vm)"    # remove a chave de host da VM anterior
ansible-playbook -i ansible/inventory.ini ansible/playbook.yml
./implantar.sh
```

## Solução de problemas

**`Permission denied` em arquivo `.qcow2` no `tofu apply`:** o AppArmor bloqueia o disco da VM. Aceitável apenas em laboratório local:

```bash
echo 'security_driver = "none"' | sudo tee -a /etc/libvirt/qemu.conf
sudo systemctl restart libvirtd
```

**`qemu-kvm` não encontrado:** em versões recentes do Ubuntu, use `qemu-system-x86`.

**Ansible `UNREACHABLE` após o `apply`:** o cloud-init ainda está em execução. Aguarde e tente novamente.

**VM desligada após reiniciar o computador:** `virsh -c qemu:///system start vm-treino`.

**VM recebeu outro IP:** execute `tofu plan` para confirmar que apenas o inventário será alterado e, em seguida, `tofu apply`.

**Spark: `Illegal Parquet type: INT64 (TIMESTAMP(NANOS,false))`:** o Parquet foi gravado pelo pandas com datas em nanossegundos. Execute `converter.py` e leia o arquivo `_spark.parquet`.

## Equipe

- Betânia Amâncio Pereira
- Gabriel Meneghetti Zanardo
- Giovana Muniz dos Santos
- Luis Gabriel Brito Felicio
- Luis Fernando Menezes Ferreira Leite
- Virgilio