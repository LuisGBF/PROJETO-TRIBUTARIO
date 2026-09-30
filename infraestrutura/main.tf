terraform {
  required_providers {
    libvirt = {
      source  = "dmacvicar/libvirt"
      version = "~> 0.8.3"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.5"
    }
  }
}
provider "libvirt" {
  uri = var.libvirt_uri
}
# Imagem base do Ubuntu, copiada para o pool do libvirt
resource "libvirt_volume" "base" {
  name   = "${var.nome_vm}-base.qcow2"
  pool   = var.pool
  source = pathexpand(var.imagem_base)
  format = "qcow2"
}
# Disco da VM, derivado da imagem base e redimensionado
resource "libvirt_volume" "disco" {
  name           = "${var.nome_vm}-disco.qcow2"
  pool           = var.pool
  base_volume_id = libvirt_volume.base.id
  size           = var.disco_gb * 1024 * 1024 * 1024
  format         = "qcow2"
}


# Disco do cloud-init, gerado a partir do template
resource "libvirt_cloudinit_disk" "init" {
  name = "${var.nome_vm}-cloudinit.iso"
  pool = var.pool
  user_data = templatefile("${path.module}/cloud_init.cfg", {
    nome_vm        = var.nome_vm
    usuario        = var.usuario
    ssh_public_key = trimspace(file(pathexpand(var.ssh_public_key_path)))
  })
}
# A máquina virtual
resource "libvirt_domain" "vm" {
  name       = var.nome_vm
  type       = "qemu"
  memory     = var.memoria_mb
  vcpu       = var.vcpus
  cloudinit  = libvirt_cloudinit_disk.init.id
  qemu_agent = true
 # cpu {
#  #   mode = "host-passthrough"
 # }
  disk {
    volume_id = libvirt_volume.disco.id
  }
  network_interface {
    network_name   = var.rede
    wait_for_lease = true
  }
  # Console serial: sem ele, imagens cloud podem travar no boot
  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }

}
# Inventário do Ansible gerado a partir do IP real da VM
resource "local_file" "inventario_ansible" {
  filename = "${path.module}/ansible/inventory.ini"


  file_permission = "0644"
  content = <<-EOT
[simulador]
${var.nome_vm}
ansible_host=${libvirt_domain.vm.network_interface[0].addresses[0]}
[simulador:vars]
ansible_user=${var.usuario}
ansible_ssh_private_key_file=${trimsuffix(var.ssh_public_key_path,
".pub")}
ansible_python_interpreter=/usr/bin/python3
ansible_ssh_common_args='-o StrictHostKeyChecking=accept-new'
EOT
}
output "ip_vm" {
  description = "Endereço IP atribuído à VM"
  value       = libvirt_domain.vm.network_interface[0].addresses[0]
}
output "comando_ssh" {
  description = "Comando para acessar a VM"
  value       = "ssh -i ~/.ssh/vm_pipeline ${var.usuario}@${libvirt_domain.vm.network_interface[0].addresses[0]}"
}
