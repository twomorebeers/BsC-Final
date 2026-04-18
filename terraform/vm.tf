variable "proxmox_api_url" {
	description = "Proxmox API URL, e.g. https://pve.local:8006/api2/json"
	type        = string
}

variable "proxmox_api_token_id" {
	description = "Token ID in form user@realm!token_name"
	type        = string
	sensitive   = true
}

variable "proxmox_api_token_secret" {
	description = "Token secret"
	type        = string
	sensitive   = true
}

variable "proxmox_tls_insecure" {
	description = "Skip TLS verification for self-signed certs"
	type        = bool
	default     = true
}

variable "proxmox_node" {
	description = "Proxmox node name"
	type        = string
	default     = "pve"
}

variable "lxc_vmid" {
	description = "VMID for the LXC"
	type        = number
	default     = 210
}

variable "lxc_hostname" {
	description = "Hostname for the Docker LXC"
	type        = string
	default     = "soho-docker"
}

variable "ostemplate" {
	description = "Container template path on Proxmox storage"
	type        = string
	default     = "local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst"
}

variable "rootfs_storage" {
	description = "Storage for rootfs"
	type        = string
	default     = "local-lvm"
}

variable "rootfs_size" {
	description = "Rootfs size"
	type        = string
	default     = "20G"
}

variable "bridge" {
	description = "Proxmox bridge"
	type        = string
	default     = "vmbr0"
}

variable "lxc_ip" {
	description = "CIDR IP for LXC, e.g. 192.168.1.50/24"
	type        = string
}

variable "gateway" {
	description = "Default gateway"
	type        = string
}

variable "lxc_root_password" {
	description = "Initial root password for the container"
	type        = string
	sensitive   = true
}

variable "ssh_public_key_path" {
	description = "Path to SSH public key used for root login"
	type        = string
	default     = "~/.ssh/id_ed25519.pub"
}

resource "proxmox_lxc" "docker_host" {
	target_node  = var.proxmox_node
	vmid         = var.lxc_vmid
	hostname     = var.lxc_hostname
	ostemplate   = var.ostemplate
	password     = var.lxc_root_password
	unprivileged = true
	onboot       = true
	start        = true

	cores  = 2
	memory = 2048
	swap   = 512

	rootfs {
		storage = var.rootfs_storage
		size    = var.rootfs_size
	}

	network {
		name   = "eth0"
		bridge = var.bridge
		ip     = var.lxc_ip
		gw     = var.gateway
	}

	features {
		nesting = true
	}

	ssh_public_keys = file(var.ssh_public_key_path)
}

output "lxc_ipv4" {
	description = "LXC IPv4 without CIDR mask"
	value       = split("/", var.lxc_ip)[0]
}

output "lxc_vmid" {
	description = "LXC VMID"
	value       = proxmox_lxc.docker_host.vmid
}
