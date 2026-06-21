# SOHO-IaC Web UI (SaaS control plane)

Self-service frontend + API that provisions an **isolated, on-demand security
stack per user** on Hetzner Cloud, then hands back a WireGuard config and an
embedded Grafana dashboard. The heavy lifting reuses the repo's existing
Terraform + Ansible pipeline.

```
register/login ─► POST /api/provision ─► terraform apply (1 Hetzner VM)
                                       ─► ansible deploy stack
                                       ─► fetch WireGuard peer config
user polls /api/provision/status ◄─────┘
         ─► scan WireGuard QR + view Grafana ─► DELETE /api/provision (destroy)
```

Each user maps to a Terraform **workspace**, so tenants never share state.
Hetzner bills hourly, so deploy-on-register / destroy-on-teardown keeps cost
near zero.

## Layout
- `api/` — FastAPI control plane (`main.py`) + provisioning logic (`provisioning.py`)
- `frontend/` — Vite + React single-page app

## Run the API
```bash
cd webui/api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export HCLOUD_TOKEN="<your-hetzner-cloud-token>"
# Optional overrides (defaults shown):
# export SOHO_SSH_USER=root
# export SOHO_SSH_KEY=~/.ssh/id_ed25519
# export WEBUI_CORS_ORIGINS=http://localhost:5173

uvicorn main:app --reload --port 8000
```
The control-plane host needs `terraform`, `ansible-playbook`, and `ssh` on PATH,
plus the SSH key referenced by the Terraform `ssh_public_key_path` variable.

## Run the frontend
```bash
cd webui/frontend
npm install
npm run dev          # http://localhost:5173
# Point at a non-default API with: VITE_API_URL=http://host:8000 npm run dev
```

## Notes / scope
- Auth and tenant state are **in-memory** (lost on restart) — fine for a thesis
  demo, not production. Swap for a DB + real sessions to harden.
- Provisioning runs in a background thread per request; the UI polls
  `/api/provision/status` for live logs.
