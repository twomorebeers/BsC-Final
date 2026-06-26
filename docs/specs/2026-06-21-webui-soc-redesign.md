# Web UI Redesign — SOC Dashboard

**Date:** 2026-06-21
**Status:** Approved (design); implementation plan pending
**Component:** `webui/` (React frontend + FastAPI control plane)

## 1. Goal

Turn the functional-but-plain single-page Web UI into a sophisticated,
multi-tab **Security Operations Center (SOC)** dashboard with a deliberate
"wow effect" for the bachelor-thesis jury, while keeping every feature real and
defensible. The redesign reuses the existing provisioning flow untouched and
adds a tabbed console plus thin live-data endpoints on the control plane.

### Success criteria
- The deploy flow still works; provisioning is now shown as a staged, animated
  progression rather than a flat log dump.
- Four additional tabs present live tenant data with a coherent SOC aesthetic.
- The resilience tab demonstrates a **real, measured** recovery-time (RTO),
  the thesis's headline metric.
- The browser only ever talks to our own API (no CORS, no exposed secrets).

### Non-goals (YAGNI)
- No persistence / database (auth + jobs stay in-memory, as today).
- No production hardening of auth or sessions.
- No multi-dashboard Grafana authoring beyond the existing `soho-overview`.
- "Ads blocked since connect" counter and chaos-run history are **optional**
  stretch items, implemented only if cheap.

## 2. Architecture

### 2.1 Frontend shell & routing
- Add `react-router-dom`.
- **Pre-provision:** the app stays on the Home/deploy view — no nav chrome, to
  keep focus on the provisioning moment.
- **When `status === "ready"`:** a persistent **left sidebar console** unlocks
  with five routes, a live tenant status chip (●Online), and sign-out.
- Routes: `/` (Home), `/metrics`, `/dns`, `/resilience`, `/devices`.
- Tabs are **gated**: deep-linking to a data route before the stack exists
  redirects to Home.
- Polling for `status` continues to drive shell state (idle/provisioning/
  ready/destroying/error), as it does today.

### 2.2 Design system (SOC)
Formalized as CSS custom properties in `styles.css`:
- **Palette:** near-black base (`#0a0e14`), raised panels (`#11161f`), hairline
  grid borders. Signal-coded accents: **cyan `#3ddbd9`** = active/normal,
  **green** = all-clear, **amber** = degraded/restarting, **red** = down/blocked.
  Color carries meaning, not just decoration.
- **Typography:** `system-ui` for prose; a **monospace** stack (`ui-monospace`)
  for all live data — query stream, RTO timer, container states — to sell the
  console feel.
- **Motion (restrained):** status dots pulse on state change; numeric counters
  roll up; faint grid/scanline texture; smooth route fade transitions.
- Reduced-motion media query disables non-essential animation.

### 2.3 Data access — control-plane proxy
The browser never contacts tenant VMs directly. The control plane already knows
each tenant's VM IP (`JOBS[tenant].result["ip"]`) and can reach it over HTTP
(Pi-hole) and SSH (Docker / WireGuard). New endpoints fetch upstream, normalize
to clean JSON, and reuse the existing bearer-token auth. This avoids CORS,
mixed-content, and exposing the Pi-hole password to the client.

All new endpoints require auth and a provisioned, `ready` tenant; otherwise they
return `409` (not ready) or `404` (no data), which the UI renders as a graceful
empty state.

## 3. Tabs

### 3.1 Home `/`
- **Deploying state:** existing stepper + live logs, restyled as an SOC console,
  plus a **stage tracker** (Terraform → cloud-init → Ansible → WireGuard) that
  advances by matching known log milestones emitted by `provisioning.py`.
- **Online state:** hero with ●Online status, tenant ID, VM IP, an "up since"
  timer, a quick stat row (blocked today / devices / services up), and the
  WireGuard connect card. Links into the other tabs.

### 3.2 Metrics `/metrics`
- Full-height embedded Grafana (`soho-overview`, `kiosk`, dark theme) inside a
  titled SOC panel. Embedding is already enabled
  (`GF_SECURITY_ALLOW_EMBEDDING=true`, anonymous viewer).

### 3.3 DNS `/dns`
- **Stat cards** (rolling counters): Queries (24h), Blocked, Block %, Active
  clients.
- **Live query-log table:** recent DNS queries (domain · client · type ·
  status), blocked rows red, allowed cyan, newest first, polled every few
  seconds with a subtle insert animation.
- **Top blocked domains** list.
- Data: `/api/pihole/summary`, `/api/pihole/queries`, `/api/pihole/top-blocked`.

### 3.4 Resilience `/resilience`
- **Service-health grid:** every container shown with a pulsing up/down dot,
  uptime, and image; polls `/api/services`.
- **Chaos panel:** a target picker **populated only with whitelisted-safe
  containers** (e.g. `n8n`, `grafana`) but presented neutrally — no "safe" or
  "restricted" labels anywhere in the UI, so the feature reads as fully general.
  "Run recovery test" calls `POST /api/chaos`; a **live RTO timer** runs while
  the UI polls `/api/services`, the target's dot transitions red→amber→green,
  and the timer freezes at the measured recovery time.
- The safe whitelist is enforced **server-side**; a request to kill a
  non-whitelisted container returns `403`.

### 3.5 Devices `/devices`
- Canonical WireGuard connect card (QR + download `.conf`).
- **Peer status** via `docker exec wireguard wg show` over SSH → last handshake,
  transfer, connected/idle. Degrades gracefully to just the QR card if `wg show`
  returns nothing.
- *(Optional)* "ads blocked since you connected" counter, derived from a
  Pi-hole stats delta captured at session start.

## 4. Backend endpoints (FastAPI, `webui/api`)

All under the existing `current_user` dependency. Tenant IP resolved from the
in-memory job result; `409` if the tenant is not `ready`.

| Method | Path | Returns |
|---|---|---|
| GET | `/api/pihole/summary` | `{queries, blocked, block_pct, clients}` |
| GET | `/api/pihole/queries?limit=N` | `[{ts, domain, client, type, status}]` |
| GET | `/api/pihole/top-blocked` | `[{domain, count}]` |
| GET | `/api/services` | `[{name, state, status, uptime, image}]` |
| POST | `/api/chaos` | `{target}` → `{ok, started_at}` (403 if not whitelisted) |
| GET | `/api/wireguard/peers` | `[{name, last_handshake, transfer, online}]` |

Implementation notes:
- **Pi-hole v6 auth:** `POST http://{ip}/api/auth` with the app password
  (`FTLCONF_webserver_api_password`, currently `admin`) → session ID (SID);
  cache the SID per tenant with TTL and refresh on `401`. Source the password
  from an env var on the control plane, not hardcoded.
- **Services:** SSH `docker ps --format '{{json .}}'` (and `docker inspect` for
  uptime if needed); parse to the table shape.
- **Chaos:** SSH `docker kill <target>` after whitelist check; recovery is
  observed by the client polling `/api/services` until the target is `running`
  again (restart policy `unless-stopped` brings it back). RTO is measured
  client-side from the POST response to the first healthy poll.
- **Peers:** SSH `docker exec wireguard wg show`.
- A small new module `webui/api/tenant_data.py` houses the SSH/HTTP helpers,
  reusing the SSH approach from `provisioning.py` (extract a shared `_ssh`).

## 5. Error handling
- Any upstream failure (SSH timeout, Pi-hole unreachable) → endpoint returns a
  structured error; the UI shows a per-card "data unavailable" state, never a
  blank screen or crash.
- Stale bearer token → existing 401 handling (drop token, return to login).
- Chaos timeout: if the target isn't healthy within a cap (e.g. 60s), the timer
  stops and shows "recovery exceeded threshold" rather than spinning forever.

## 6. Testing
- **Backend:** unit-test the proxy/normalization helpers with mocked SSH/HTTP
  (Pi-hole JSON → summary shape; `docker ps` JSON → services shape; chaos
  whitelist enforcement returns 403 for disallowed targets).
- **Frontend:** component-level checks that each tab renders its loading, ready,
  and error states; the stage tracker maps known log lines to stages; the RTO
  timer starts/stops on the right transitions.
- **Manual:** end-to-end against a real provisioned tenant before the demo.

## 7. Risks & mitigations
- *Live chaos disrupting the demo* → mitigated by the server-side safe whitelist
  (§3.4).
- *Pi-hole API shape differences across versions* → isolate parsing in
  `tenant_data.py`; one place to adjust.
- *Secrets in history* (pre-existing) → out of scope here; tracked separately.
- *In-memory state lost on API restart* → acceptable per thesis scope; a restart
  mid-demo means re-login + the tenant data tabs show empty until re-resolved.

## 8. Scope / phasing (for the implementation plan)
1. Frontend shell: router, sidebar, SOC design tokens, gated routes.
2. Home redesign (stage tracker + online hero) — no new backend.
3. Metrics tab (Grafana embed) — no new backend.
4. Backend: `tenant_data.py` + Pi-hole/services/peers endpoints.
5. DNS tab.
6. Resilience tab + `/api/chaos`.
7. Devices tab.
8. Optional stretch items.
