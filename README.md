# Pipeline Tributário

**Automação e Escalabilidade de Pipelines de Big Data e Análise de Dados**
*Diagnóstico Automatizado de Enquadramento Tributário para Consultoria Contábil*

Pipeline que compara a carga tributária estimada de empresas nos regimes Simples Nacional, Lucro Presumido e Lucro Real. Este repositório contém a infraestrutura como código que provisiona a máquina virtual e o simulador que gera, dentro dela, a movimentação econômico-financeira das empresas.

| Etapa | Ferramenta | Função |
|---|---|---|
| Provisionamento | OpenTofu + libvirt/KVM | Cria a VM Ubuntu 24.04 e gera o inventário do Ansible |
| Configuração inicial | cloud-init | Usuário, acesso SSH por chave e hostname |
| Preparação do ambiente | Ansible | Python, ambiente virtual, dependências e diretórios |
| Implantação | SCP | Transfere o simulador para a VM |
| Geração de dados | Simulador em Python | Produz os lançamentos em CSV na VM |

## Estrutura

```
infraestrutura/
├── main.tf, variables.tf     # provisionamento da VM
├── cloud_init.cfg            # configuração do primeiro boot
├── implantar.sh              # transferência do simulador por SCP
└── ansible/
    ├── inventory.ini         # gerado automaticamente pelo OpenTofu
    └── playbook.yml          # preparação do ambiente
simulador/
├── simulador.py              # gerador de dados
└── requirements.txt
dados/
└── exemplo_dados.csv         # exemplo gerado na VM
```

## Pré-requisitos

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

## Execução

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

# 3. Preparar o ambiente
ansible -i ansible/inventory.ini simulador -m ping
ansible-playbook -i ansible/inventory.ini ansible/playbook.yml

# 4. Transferir o simulador por SCP
./implantar.sh

# 5. Executar o simulador na VM
ssh -i ~/.ssh/vm_pipeline pipeline@$(tofu output -raw ip_vm)
cd /opt/simulador
./venv/bin/python simulador.py --registros 50 --saida /var/lib/simulador/dados | tee -a /var/log/simulador/execucoes.log
ls -l /var/lib/simulador/dados          # um arquivo novo por execução
```

O playbook é idempotente: uma segunda execução termina com `changed=0`. Código e dados ficam separados, em `/opt/simulador` e `/var/lib/simulador/dados`, e cada execução do simulador gera um novo arquivo, sem sobrescrever os anteriores.

## Simulador

Gera lançamentos mensais de empresas fictícias com as variáveis necessárias ao cálculo tributário, ausentes da base pública da Receita Federal.

| Grupo | Campos |
|---|---|
| Identificação | `id_lancamento`, `cnpj_basico` |
| Classificação | `macro_setor`, `cnae_fiscal_principal`, `regime_atual` |
| Valores do mês | `receita_bruta_mensal`, `folha_salarios_mensal`, `custo_mercadoria_vendida`, `despesas_operacionais`, `compras_com_credito` |
| Temporal | `competencia`, `data_hora_geracao` |

Parâmetros: `--registros` (mínimo 10, padrão 50), `--saida`, `--competencia` (AAAA-MM), `--semente` e `--taxa-defeitos` (padrão 0,10). Uma parcela dos registros recebe problemas de qualidade controlados — valores ausentes, formatos divergentes, categorias inconsistentes, discrepantes e duplicatas —, tratados nas etapas seguintes do pipeline. Use `--taxa-defeitos 0` para gerar dados limpos.

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

## Equipe

- Betânia Amâncio Pereira
- Gabriel Meneghetti Zanardo
- Giovana Muniz dos Santos
- Luis Gabriel Brito Felicio
- Luis Fernando Menezes Ferreira Leite

