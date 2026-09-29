variable "libvirt_uri" {
description = "Endereço de conexão com o libvirt da máquina hospedeira"
type = string
default = "qemu:///system"
}
variable "nome_vm" {
description = "Nome da máquina virtual"
type = string
default = "vm-treino"
}
variable "memoria_mb" {
description = "Memória RAM da VM em MB"
type = number
default = 2048

}
variable "vcpus" {
description = "Quantidade de CPUs virtuais"
type = number
default = 2
}
variable "disco_gb" {
description = "Tamanho do disco da VM em GB"
type = number
default = 10
}
variable "pool" {
description = "Pool de armazenamento do libvirt"
type = string
default = "default"
}
variable "rede" {
description = "Rede virtual do libvirt"
type = string
default = "default"
}
variable "imagem_base" {
description = "Caminho local da imagem cloud do Ubuntu"
type = string
default = "~/imagens-vm/noble-server-cloudimg-amd64.img"
}
variable "usuario" {
description = "Usuário criado pelo cloud-init"
type = string
default = "pipeline"
}
variable "ssh_public_key_path" {
description = "Caminho da chave pública SSH autorizada a acessar a VM"

type = string
default = "~/.ssh/vm_pipeline.pub"
}
