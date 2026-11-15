# VM de monitoramento: Prometheus e Grafana acompanham a VM geradora

# Disco da VM de monitoramento, derivado da mesma imagem base da VM geradora
resource "libvirt_volume" "disco_monitoramento" {
  name           = "${var.nome_vm_monitoramento}-disco.qcow2"
  pool           = var.pool
  base_volume_id = libvirt_volume.base.id
  size           = var.disco_gb * 1024 * 1024 * 1024
  format         = "qcow2"
}

# Disco do cloud-init, gerado a partir do mesmo template
resource "libvirt_cloudinit_disk" "init_monitoramento" {
  name = "${var.nome_vm_monitoramento}-cloudinit.iso"
  pool = var.pool
  user_data = templatefile("${path.module}/cloud_init.cfg", {
    nome_vm        = var.nome_vm_monitoramento
    usuario        = var.usuario
    ssh_public_key = trimspace(file(pathexpand(var.ssh_public_key_path)))
  })
}

# A máquina virtual de monitoramento
resource "libvirt_domain" "monitoramento" {
  name       = var.nome_vm_monitoramento
  memory     = var.memoria_mb
  vcpu       = var.vcpus
  cloudinit  = libvirt_cloudinit_disk.init_monitoramento.id
  qemu_agent = false

  cpu {
    mode = "host-passthrough"
  }

  disk {
    volume_id = libvirt_volume.disco_monitoramento.id
  }

  network_interface {
    network_name   = var.rede
    wait_for_lease = true
  }

  console {
    type        = "pty"
    target_type = "serial"
    target_port = "0"
  }
}

output "ip_monitoramento" {
  description = "Endereço IP da VM de monitoramento"
  value       = libvirt_domain.monitoramento.network_interface[0].addresses[0]
}

output "url_grafana" {
  description = "Endereço do Grafana no navegador"
  value       = "http://${libvirt_domain.monitoramento.network_interface[0].addresses[0]}:3000"
}