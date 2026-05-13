# SOHO IaC Thesis Project

Infrastructure-as-Code project for deploying and operating a SOHO security stack using:

- Terraform (Proxmox LXC provisioning)
- Ansible (host bootstrap + Docker deployment)
- Docker Compose (services)
- Python CLI (`soho_iac.py`) for orchestration and status

## Overview

This repository implements an end-to-end IaC workflow for a home/small-office environment:

1. Provision an LXC on Proxmox with Terraform
2. Configure the host and deploy containers with Ansible
3. Run the security stack with Docker Compose:
	 - Pi-hole (DNS filtering)
	 - Unbound (recursive DNS)
	 - WireGuard (VPN)
	 - Nginx Proxy Manager (reverse proxy)
	 - n8n (automation)

The Python CLI can run deployment steps and show service status using real `docker ps` output (local or remote via SSH/Proxmox).

## Repository Layout

```text
.
├── soho_iac.py
├── terraform/
│   ├── main.tf
│   ├── vm.tf
│   ├── cloud-init.yml
│   └── credentials.tfvars
├── ansible/
│   ├── inventory.ini
│   └── playbook.yaml
└── docker/
		├── docker-compose.yml
		├── docker-compose-demo.yml
		└── config/
```

## Prerequisites

Install the following on your control machine:

- Python 3.10+
- Terraform 1.5+
- Ansible (and `community.docker` collection)
- Docker CLI
- SSH access to Proxmox and/or target LXC

Optional but recommended:

- `rich` Python package for nicer CLI output

## Terraform Configuration (Proxmox)

The Proxmox provider is configured in `terraform/main.tf`, and LXC resources/variables are in `terraform/vm.tf`.

Edit `terraform/credentials.tfvars` with real values:

- `proxmox_api_url`
- `proxmox_api_token_id`
- `proxmox_api_token_secret`
- `proxmox_node`
- `lxc_ip`, `gateway`
- `lxc_root_password`
- `ssh_public_key_path`

> Important: never commit real secrets.

## Ansible Configuration

Main playbook: `ansible/playbook.yaml`.

Inventory can be:

- generated automatically by `soho_iac.py deploy` from Terraform output (`lxc_ipv4`), or
- set manually in `ansible/inventory.ini`.

## Docker Stack

- Production-style compose: `docker/docker-compose.yml`
- Demo compose (portable host ports): `docker/docker-compose-demo.yml`

## Python CLI (`soho_iac.py`)

Run:

```bash
python3 soho_iac.py help
```

Commands:

- `deploy` – runs Terraform + Ansible pipeline
- `status` – prints service table (prefers real Docker status)
- `destroy` – simulated destruction workflow
- `restore` – simulated recovery workflow with RTO timer

## Getting Real `docker ps` Data in `status`

`soho_iac.py status` uses this priority:

1. Direct SSH to Docker host (`SOHO_DOCKER_SSH`)
2. SSH to Proxmox + `pct exec` into LXC (`SOHO_PROXMOX_SSH` + `SOHO_LXC_ID`)
3. Local Docker daemon
4. Fallback demo data

Set environment variables (example):

```bash
export SOHO_DOCKER_SSH="root@192.168.100.50"

# OR (Proxmox hop)
export SOHO_PROXMOX_SSH="root@192.168.100.10"
export SOHO_LXC_ID="210"

# Optional for generated Ansible inventory
export SOHO_LXC_SSH_USER="root"
export SOHO_LXC_SSH_KEY="~/.ssh/id_ed25519"
```

Then run:

```bash
python3 soho_iac.py status
```

## Typical End-to-End Flow

```bash
# 1) Provision LXC in Proxmox
cd terraform
terraform init
terraform apply -var-file=credentials.tfvars

# 2) Return to project root and run orchestrator
cd ..
python3 soho_iac.py deploy

# 3) Check service status
python3 soho_iac.py status
```

## Troubleshooting

- `status` shows demo data:
	- verify SSH connectivity and key auth
	- verify env vars are set in the same shell session
	- verify Docker is installed and running inside LXC
- Terraform fails to authenticate:
	- verify token ID/secret and API URL format
	- if you see x509 TLS errors, set `proxmox_tls_insecure = true` (lab/self-signed)
- Ansible cannot connect:
	- check generated `ansible/inventory.ini`
	- ensure `ansible_ssh_private_key_file` points to a private key (no `.pub`)
	- if you see “REMOTE HOST IDENTIFICATION HAS CHANGED”, clear the old key or use a dedicated `known_hosts_soho` file
	- verify SSH user/key and host reachability

## Security Notes

- Replace all placeholder passwords immediately
- Do not store secrets in Git
- Consider moving sensitive values to a secrets manager or CI/CD secret store

## License

Academic project (Bachelor thesis). Add your preferred open-source license if distributing publicly.
