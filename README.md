# SOHO IaC Thesis Project

Infrastructure-as-Code project that delivers a SOHO security stack as a
**self-service, on-demand service**. A user registers in a web UI, and a full
isolated stack is provisioned for them on a cloud VM, configured, and handed
back as a WireGuard connection plus a friendly dashboard.

Stack of tools:

- **Terraform** — provisions a Hetzner Cloud VM (per tenant, on demand)
- **Ansible** — bootstraps the host and deploys the containers
- **Docker Compose** — runs the security/observability services
- **Web UI** (`webui/`) — FastAPI control plane + React frontend (the SaaS layer)

## Why this design

The original stack assumed the user owned a server (Proxmox) and the skills to
run it. The accessibility goal — *help non-technical home users* — is met by
**not** running anything on the user's hardware. Instead:

- The stack runs on a throwaway **Hetzner VM** provisioned per tenant.
- The user only needs a **WireGuard client** (every OS has one) and a browser.
- Hetzner bills hourly, so the control plane provisions on demand and destroys
  on teardown — cost stays near zero.

The same Terraform + Ansible pipeline is what makes "provision a fresh, isolated
stack in minutes" possible, and the measured provision/destroy time is the
thesis's resilience (RTO) metric.

## Services

| Container | Layer | Notes |
|---|---|---|
| Pi-hole | DNS filtering | Network-wide ad/tracker blocking |
| Unbound | Recursive DNS | Local resolution (privacy) |
| WireGuard | VPN | How the user's device reaches the stack |
| Nginx Proxy Manager | Reverse proxy | |
| n8n | Automation | |
| Pi-hole exporter → Prometheus → Grafana | Observability | Dashboards embedded in the Web UI |

## Repository layout

```text
.
├── terraform/             # Hetzner provisioning (per-tenant workspaces)
│   ├── main.tf            #   hcloud provider
│   ├── hetzner.tf         #   server resource, variables, outputs
│   └── cloud-init.yml
├── ansible/               # host bootstrap + Docker deploy
│   ├── inventory.ini      #   auto-generated from Terraform output
│   └── playbook.yaml
├── docker/                # the service stack + observability config
│   ├── docker-compose.yml
│   └── config/
└── webui/                 # SaaS control plane
    ├── api/               #   FastAPI + provisioning logic
    └── frontend/          #   React (Vite)
```

## Prerequisites (control-plane host)

- Python 3.10+, Terraform 1.5+, Ansible (+ `community.docker` collection)
- `ssh` on PATH and an SSH keypair (default `~/.ssh/id_ed25519[.pub]`)
- A **Hetzner Cloud API token** (Read & Write)
- Node.js (for the React frontend)

## The Hetzner token (never commit it)

The token is read from the environment, forwarded to Terraform as
`TF_VAR_hcloud_token`, and never written to a file:

```bash
export HCLOUD_TOKEN="hcloud_xxxxxxxxxxxxxxxxxxxx"
```

`terraform/credentials.tfvars` holds only **non-secret** tunables
(`tenant_id`, server type, location, SSH key path); it is gitignored. See
`terraform/credentials.tfvars.example`.

## Quick start — the Web UI (primary path)

See `webui/README.md`. In short:

```bash
# API
cd webui/api && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export HCLOUD_TOKEN="..."
uvicorn main:app --reload --port 8000

# Frontend (separate shell)
cd webui/frontend && npm install && npm run dev   # http://localhost:5173
```

Register → "Deploy my network" → scan the WireGuard QR → watch your Grafana.
"Tear down" destroys the VM.

## Security notes

- Never commit the Hetzner token, `terraform/credentials.tfvars`, or
  `*.tfstate` (state stores secrets in plaintext). These are gitignored.
- Rotate any token that was ever committed — removing the file does not purge
  git history.

## License

Academic project (Bachelor thesis). Add a license before distributing publicly.
