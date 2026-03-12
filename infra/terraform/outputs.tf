output "ssh_command" {
  description = "SSH command to connect to the VPS"
  value       = "ssh -p ${var.vps_ssh_port} ${var.vps_user}@${var.vps_host}"
}

output "app_dir" {
  description = "Deployment directory on the VPS"
  value       = var.app_dir
}

output "compose_command" {
  description = "Run docker compose commands on the VPS"
  value       = "ssh -p ${var.vps_ssh_port} ${var.vps_user}@${var.vps_host} 'cd ${var.app_dir} && docker compose'"
}
