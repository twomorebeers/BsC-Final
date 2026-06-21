# Hetzner Cloud — on-demand, per-tenant provisioning.
#
# Each tenant gets its own Terraform workspace, so `tenant_id` keeps server
# names / SSH keys unique per customer. Hetzner bills hourly, so the SaaS
# control plane can `apply` on registration and `destroy` when the session
# ends, keeping cost near zero.

variable "hcloud_token" {
  description = "Hetzner Cloud API token (set via TF_VAR_hcloud_token, never committed)"
  type        = string
  sensitive   = true
}

variable "tenant_id" {
  description = "Unique tenant/customer identifier (used for naming + workspace)"
  type        = string
  default     = "demo"
}

variable "hcloud_server_type" {
  description = "Hetzner server type (x86 Intel/AMD; cx23 = Intel shared, available in Falkenstein)"
  type        = string
  default     = "cx23"
}

variable "hcloud_location" {
  description = "Hetzner datacenter (nbg1=Nuremberg, fsn1=Falkenstein, hel1=Helsinki)"
  type        = string
  default     = "fsn1"
}

variable "hcloud_image" {
  description = "Base OS image"
  type        = string
  default     = "ubuntu-22.04"
}

variable "ssh_public_key_path" {
  description = "Path to the SSH public key injected into the VM for root login"
  type        = string
  default     = "/Users/bogdishor/.ssh/id_ed25519.pub"
}

# No hcloud_ssh_key resource: Hetzner SSH keys must be unique by fingerprint,
# so creating one per tenant from the same public key collides after the first.
# Inject the operator's public key via cloud-init instead — unlimited tenants,
# no shared global resource.
resource "hcloud_server" "tenant" {
  name        = "soho-${var.tenant_id}"
  server_type = var.hcloud_server_type
  image       = var.hcloud_image
  location    = var.hcloud_location
  user_data = templatefile("${path.module}/cloud-init.yml.tftpl", {
    ssh_public_key = trimspace(file(var.ssh_public_key_path))
  })

  labels = {
    project = "soho-iac"
    tenant  = var.tenant_id
  }
}

output "server_ipv4" {
  description = "Public IPv4 of the provisioned tenant VM"
  value       = hcloud_server.tenant.ipv4_address
}

output "server_id" {
  description = "Hetzner server id"
  value       = tostring(hcloud_server.tenant.id)
}
