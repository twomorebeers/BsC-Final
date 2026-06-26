# SOC Web UI Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the `webui/` frontend into a gated, multi-tab Security-Operations-Center dashboard (Home / Metrics / DNS / Resilience / Devices) backed by thin live-data proxy endpoints on the FastAPI control plane.

**Architecture:** The React SPA gains client-side routing and an app shell that unlocks once a tenant is provisioned. New FastAPI endpoints fetch live data from the tenant VM (Pi-hole v6 over HTTP, Docker/WireGuard over SSH), normalize it to JSON, and reuse the existing bearer-token auth so the browser never talks to the VM directly. Provisioning flow is unchanged.

**Tech Stack:** React 18 + Vite + react-router-dom, Vitest for frontend logic tests; FastAPI + httpx for the Pi-hole client, pytest for backend tests; SSH via the existing `subprocess` helper.

## Global Constraints

- Secrets via env vars, never files (`HCLOUD_TOKEN`, and a new `PIHOLE_API_PASSWORD`, default `admin`).
- No database / persistence — `USERS`, `TOKENS`, `JOBS` stay in-memory (DB explicitly out of scope).
- All new endpoints require `current_user`; return `409` if the tenant is not `ready`, `404` if no data, `403` for a disallowed chaos target.
- The chaos safe-whitelist is `{"n8n", "grafana"}`, enforced server-side; never labeled in the UI.
- SOC palette tokens: base `#0a0e14`, panel `#11161f`, cyan `#3ddbd9` (active), green (ok), amber (degraded), red (down/blocked). Monospace for live data.
- Respect `prefers-reduced-motion` for all animation.
- Frontend dev server: `http://localhost:5173`; API: `http://localhost:8000`.

---

## File Structure

**Frontend (`webui/frontend/`)**
- `package.json` — add `react-router-dom`, `vitest`, `@testing-library/react`, `jsdom`.
- `src/main.jsx` — wrap app in `<BrowserRouter>`.
- `src/App.jsx` — auth gate → either Home (pre-ready) or the routed Shell.
- `src/styles.css` — SOC design tokens + shell/sidebar/card styles.
- `src/api.js` — extend with the new data calls.
- `src/lib/stages.js` — pure log-line → provisioning-stage mapping.
- `src/hooks/usePolling.js` — interval fetch hook with cleanup.
- `src/components/{Shell,Sidebar,StatCard,Counter,StatusDot,WireguardCard}.jsx`.
- `src/pages/{Home,Metrics,Dns,Resilience,Devices}.jsx`.
- `src/lib/stages.test.js`, `src/components/Counter.test.jsx` — Vitest.

**Backend (`webui/api/`)**
- `tenant_data.py` — tenant IP resolution, Pi-hole client (+ SID cache), `docker ps` → services, `wg show` → peers, chaos whitelist.
- `main.py` — wire the new routes.
- `requirements.txt` — add `httpx`.
- `tests/test_tenant_data.py` — parsing/normalization + whitelist tests.

---

## Phase 1 — Frontend shell & design system

### Task 1: Tooling, deps, and SOC design tokens

**Files:**
- Modify: `webui/frontend/package.json`
- Modify: `webui/frontend/src/styles.css`
- Create: `webui/frontend/vitest.config.js`

**Interfaces:**
- Produces: CSS custom properties (`--bg`, `--panel`, `--accent`, `--ok`, `--warn`, `--danger`, `--mono`) and `.shell`, `.sidebar`, `.statcard`, `.dot` classes used by every later task.

- [ ] **Step 1: Add dependencies**

In `webui/frontend/package.json`, add to `dependencies`: `"react-router-dom": "^6.26.0"`. Add to `devDependencies`: `"vitest": "^2.0.0"`, `"@testing-library/react": "^16.0.0"`, `"@testing-library/jest-dom": "^6.4.0"`, `"jsdom": "^24.0.0"`. Add script `"test": "vitest run"`.

- [ ] **Step 2: Install**

Run: `cd webui/frontend && npm install`
Expected: exits 0, `node_modules/react-router-dom` exists.

- [ ] **Step 3: Vitest config**

Create `webui/frontend/vitest.config.js`:
```js
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: { environment: "jsdom", globals: true, setupFiles: [] },
});
```

- [ ] **Step 4: SOC tokens**

Replace the `:root` block in `src/styles.css` and append shell styles:
```css
:root {
  --bg: #0a0e14;
  --panel: #11161f;
  --line: #1d2530;
  --text: #e6edf3;
  --muted: #7d8794;
  --accent: #3ddbd9;   /* active / normal */
  --ok: #3fb950;       /* all-clear */
  --warn: #d29922;     /* degraded / restarting */
  --danger: #f85149;   /* down / blocked */
  --mono: ui-monospace, "SF Mono", "JetBrains Mono", Menlo, monospace;
}
.shell { display: grid; grid-template-columns: 220px 1fr; min-height: 100vh; }
.sidebar { background: var(--panel); border-right: 1px solid var(--line); padding: 1rem; display: flex; flex-direction: column; gap: .25rem; }
.sidebar a { color: var(--muted); text-decoration: none; padding: .5rem .7rem; border-radius: 8px; font-size: .92rem; }
.sidebar a.active { color: var(--text); background: #161d28; box-shadow: inset 2px 0 0 var(--accent); }
.content { padding: 1.5rem; max-width: 1100px; }
.statcard { background: var(--panel); border: 1px solid var(--line); border-radius: 12px; padding: 1rem 1.2rem; }
.statcard .n { font-family: var(--mono); font-size: 1.8rem; font-weight: 700; }
.dot { width: 9px; height: 9px; border-radius: 999px; display: inline-block; }
.dot.up { background: var(--ok); } .dot.warn { background: var(--warn); } .dot.down { background: var(--danger); }
@media (prefers-reduced-motion: no-preference) { .dot.warn { animation: pulse 1s ease-in-out infinite; } }
@keyframes pulse { 50% { opacity: .35; } }
.statgrid { display: grid; grid-template-columns: repeat(auto-fit,minmax(160px,1fr)); gap: 1rem; }
.qtable { width: 100%; border-collapse: collapse; font-family: var(--mono); font-size: .82rem; }
.qtable td, .qtable th { text-align: left; padding: .35rem .5rem; border-bottom: 1px solid var(--line); }
.q-blocked { color: var(--danger); } .q-ok { color: var(--accent); }
```

- [ ] **Step 5: Verify the app still builds**

Run: `cd webui/frontend && npm run build`
Expected: build succeeds (existing App still compiles; tokens only changed).

- [ ] **Step 6: Commit**

```bash
git add webui/frontend/package.json webui/frontend/package-lock.json webui/frontend/vitest.config.js webui/frontend/src/styles.css
git commit -m "feat(webui): add router/test deps and SOC design tokens"
```

### Task 2: Router, app shell, sidebar, polling hook

**Files:**
- Modify: `webui/frontend/src/main.jsx`
- Modify: `webui/frontend/src/App.jsx`
- Create: `webui/frontend/src/hooks/usePolling.js`
- Create: `webui/frontend/src/components/Shell.jsx`
- Create: `webui/frontend/src/components/Sidebar.jsx`

**Interfaces:**
- Consumes: `api.status()`, `api.hasToken()` (existing).
- Produces: `usePolling(fn, ms, deps)`; `<Shell status={...} onLogout={...} />` renders `<Sidebar>` + `<Outlet context={{status}}>`; routes `/ /metrics /dns /resilience /devices`.

- [ ] **Step 1: Polling hook**

Create `src/hooks/usePolling.js`:
```js
import { useEffect, useRef, useState } from "react";

export function usePolling(fn, ms, deps = []) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const saved = useRef(fn);
  saved.current = fn;
  useEffect(() => {
    let active = true;
    const tick = async () => {
      try { const d = await saved.current(); if (active) { setData(d); setError(null); } }
      catch (e) { if (active) setError(e); }
    };
    tick();
    const id = setInterval(tick, ms);
    return () => { active = false; clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error };
}
```

- [ ] **Step 2: Sidebar**

Create `src/components/Sidebar.jsx`:
```jsx
import { NavLink } from "react-router-dom";

const TABS = [
  ["/", "Overview"],
  ["/metrics", "Metrics"],
  ["/dns", "DNS"],
  ["/resilience", "Resilience"],
  ["/devices", "Devices"],
];

export default function Sidebar({ onLogout }) {
  return (
    <nav className="sidebar">
      <strong style={{ padding: ".5rem .7rem 1rem" }}>SOHO‑IaC</strong>
      {TABS.map(([to, label]) => (
        <NavLink key={to} to={to} end={to === "/"}
          className={({ isActive }) => (isActive ? "active" : "")}>
          {label}
        </NavLink>
      ))}
      <span style={{ flex: 1 }} />
      <button className="link" onClick={onLogout}>Sign out</button>
    </nav>
  );
}
```

- [ ] **Step 3: Shell**

Create `src/components/Shell.jsx`:
```jsx
import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar.jsx";

export default function Shell({ status, onLogout }) {
  return (
    <div className="shell">
      <Sidebar onLogout={onLogout} />
      <main className="content">
        <Outlet context={{ status }} />
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Router in main.jsx**

Replace `src/main.jsx`:
```jsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
```

- [ ] **Step 5: App.jsx — auth gate + gated routes**

Replace `src/App.jsx` with auth gate, status polling, and routes. Pre-`ready` always renders Home; data tabs redirect to `/` until ready:
```jsx
import { useState } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import { api } from "./api";
import { usePolling } from "./hooks/usePolling.js";
import Shell from "./components/Shell.jsx";
import Auth from "./pages/Auth.jsx";
import Home from "./pages/Home.jsx";
import Metrics from "./pages/Metrics.jsx";
import Dns from "./pages/Dns.jsx";
import Resilience from "./pages/Resilience.jsx";
import Devices from "./pages/Devices.jsx";

export default function App() {
  const [authed, setAuthed] = useState(api.hasToken());
  if (!authed) return <Auth onAuthed={() => setAuthed(true)} />;
  return <Authed onLogout={() => { api.clearToken(); setAuthed(false); }} />;
}

function Authed({ onLogout }) {
  const { data } = usePolling(api.status, 2000, []);
  const status = data || { state: "idle", logs: [] };
  const ready = status.state === "ready";
  const gate = (el) => (ready ? el : <Navigate to="/" replace />);
  return (
    <Routes>
      <Route element={<Shell status={status} onLogout={onLogout} />}>
        <Route path="/" element={<Home status={status} />} />
        <Route path="/metrics" element={gate(<Metrics result={status.result} />)} />
        <Route path="/dns" element={gate(<Dns />)} />
        <Route path="/resilience" element={gate(<Resilience />)} />
        <Route path="/devices" element={gate(<Devices result={status.result} />)} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
```

- [ ] **Step 6: Extract Auth into its own page**

Move the existing `Auth` component from the old `App.jsx` into `src/pages/Auth.jsx` (same code, add `import { api } from "../api";` and `export default function Auth(...)`).

- [ ] **Step 7: Verify build**

Run: `cd webui/frontend && npm run build`
Expected: succeeds once Home/Metrics/Dns/Resilience/Devices stubs exist — create one-line placeholder default exports returning `<div/>` for any not yet built, to be replaced in their tasks.

- [ ] **Step 8: Commit**

```bash
git add webui/frontend/src
git commit -m "feat(webui): add router, app shell, sidebar, polling hook"
```

---

## Phase 2 — Home (Overview)

### Task 3: Provisioning stage mapping (TDD) + Home page

**Files:**
- Create: `webui/frontend/src/lib/stages.js`
- Create: `webui/frontend/src/lib/stages.test.js`
- Create: `webui/frontend/src/pages/Home.jsx`

**Interfaces:**
- Produces: `stagesFromLogs(logs: string[]) -> [{key,label,done}]` with stage keys `terraform`, `cloudinit`, `ansible`, `wireguard`.

- [ ] **Step 1: Write the failing test**

Create `src/lib/stages.test.js`:
```js
import { describe, it, expect } from "vitest";
import { stagesFromLogs } from "./stages.js";

describe("stagesFromLogs", () => {
  it("marks terraform done after apply output", () => {
    const s = stagesFromLogs(["$ terraform apply", "VM provisioned at 1.2.3.4"]);
    expect(s.find((x) => x.key === "terraform").done).toBe(true);
    expect(s.find((x) => x.key === "ansible").done).toBe(false);
  });
  it("marks all done when wireguard config fetched", () => {
    const s = stagesFromLogs(["VM ready.", "ansible-playbook", "[Interface]"]);
    expect(s.every((x) => x.done)).toBe(true);
  });
});
```

- [ ] **Step 2: Run test, verify it fails**

Run: `cd webui/frontend && npx vitest run src/lib/stages.test.js`
Expected: FAIL — "Failed to resolve import ./stages.js".

- [ ] **Step 3: Implement stages.js**

Create `src/lib/stages.js` (matches log milestones emitted by `provisioning.py`):
```js
const RULES = [
  { key: "terraform", label: "Provision VM", match: /VM provisioned at|terraform apply/i },
  { key: "cloudinit", label: "Boot & cloud-init", match: /VM ready\.|cloud-init/i },
  { key: "ansible", label: "Deploy stack", match: /ansible-playbook|docker_compose/i },
  { key: "wireguard", label: "Issue VPN config", match: /\[Interface\]|WireGuard/i },
];

export function stagesFromLogs(logs = []) {
  const text = logs.join("\n");
  return RULES.map((r) => ({ key: r.key, label: r.label, done: r.match.test(text) }));
}
```

- [ ] **Step 4: Run test, verify it passes**

Run: `cd webui/frontend && npx vitest run src/lib/stages.test.js`
Expected: PASS (2 tests).

- [ ] **Step 5: Home page**

Create `src/pages/Home.jsx` — deploy controls + stage tracker + logs, then an online hero. Uses existing `api.provision/destroy/status` shapes and `WireguardCard` (Task 11 creates it; for now inline the QR like the old Ready did):
```jsx
import { useEffect, useRef } from "react";
import { api } from "../api";
import { stagesFromLogs } from "../lib/stages.js";

export default function Home({ status }) {
  const logRef = useRef(null);
  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [status.logs]);
  const busy = status.state === "provisioning" || status.state === "destroying";
  const stages = stagesFromLogs(status.logs);

  return (
    <>
      <header><h1>Overview</h1><span className={`badge ${status.state}`}>{status.state}</span></header>

      {status.state !== "ready" && (
        <div className="card">
          <div className="row">
            {status.state === "idle" && <button onClick={() => api.provision()}>Deploy my network</button>}
            {busy && <button disabled>Working…</button>}
            <div className="spacer" />
          </div>
          <ol className="stages">
            {stages.map((s) => (
              <li key={s.key} className={s.done ? "done" : ""}>
                <span className={`dot ${s.done ? "up" : "warn"}`} /> {s.label}
              </li>
            ))}
          </ol>
          {(busy || status.logs.length > 0) && (
            <pre className="logs" ref={logRef}>{status.logs.join("\n")}</pre>
          )}
          {status.error && <div className="error">{status.error}</div>}
        </div>
      )}

      {status.state === "ready" && status.result && (
        <div className="card">
          <h2>● Online</h2>
          <p className="muted">Tenant {status.result.tenant_id} · {status.result.ip}</p>
          <button className="danger" onClick={() => api.destroy()}>Tear down</button>
        </div>
      )}
    </>
  );
}
```
Add `.stages` styling to `styles.css`:
```css
.stages { list-style: none; padding: 0; display: flex; flex-direction: column; gap: .5rem; margin: 1rem 0; }
.stages li { color: var(--muted); } .stages li.done { color: var(--text); }
```

- [ ] **Step 6: Commit**

```bash
git add webui/frontend/src/lib webui/frontend/src/pages/Home.jsx webui/frontend/src/styles.css
git commit -m "feat(webui): Home overview with provisioning stage tracker"
```

---

## Phase 3 — Metrics

### Task 4: Metrics (Grafana embed)

**Files:**
- Create: `webui/frontend/src/pages/Metrics.jsx`

**Interfaces:**
- Consumes: `result.grafana_url` (existing job result field).

- [ ] **Step 1: Implement**

Create `src/pages/Metrics.jsx`:
```jsx
export default function Metrics({ result }) {
  const src = `${result.grafana_url}/d/soho-overview?orgId=1&kiosk&theme=dark`;
  return (
    <>
      <header><h1>Metrics</h1></header>
      <div className="card" style={{ padding: 0 }}>
        <iframe title="Grafana" src={src}
          style={{ width: "100%", height: "78vh", border: 0, borderRadius: 12 }} />
      </div>
    </>
  );
}
```

- [ ] **Step 2: Manual check**

Run the API + frontend against a provisioned tenant; navigate to `/metrics`; the dashboard renders embedded.

- [ ] **Step 3: Commit**

```bash
git add webui/frontend/src/pages/Metrics.jsx
git commit -m "feat(webui): Metrics tab with embedded Grafana"
```

---

## Phase 4 — Backend live-data layer

### Task 5: tenant_data.py — IP resolution + services (`docker ps`)

**Files:**
- Create: `webui/api/tenant_data.py`
- Create: `webui/api/tests/test_tenant_data.py`
- Modify: `webui/api/requirements.txt` (add `httpx`)

**Interfaces:**
- Consumes: `provisioning._ssh(ip, cmd, timeout)`, the in-memory `JOBS` (passed in).
- Produces: `tenant_ip(job) -> str | None`; `services(ip) -> list[dict]` with keys `name,state,status,image`.

- [ ] **Step 1: Failing test for `services` parsing**

Create `webui/api/tests/test_tenant_data.py`:
```python
from unittest.mock import patch
import tenant_data

DOCKER_PS = (
    '{"Names":"pihole","State":"running","Status":"Up 3 hours","Image":"pihole/pihole:latest"}\n'
    '{"Names":"n8n","State":"running","Status":"Up 3 hours","Image":"n8nio/n8n"}\n'
)

def test_services_parses_docker_ps():
    with patch("tenant_data._ssh") as m:
        m.return_value.returncode = 0
        m.return_value.stdout = DOCKER_PS
        out = tenant_data.services("1.2.3.4")
    assert {"name": "pihole", "state": "running", "status": "Up 3 hours",
            "image": "pihole/pihole:latest"} in out
    assert len(out) == 2
```

- [ ] **Step 2: Run, verify it fails**

Run: `cd webui/api && python -m pytest tests/test_tenant_data.py -v`
Expected: FAIL — `ModuleNotFoundError: tenant_data`.

- [ ] **Step 3: Implement `tenant_ip` + `services`**

Create `webui/api/tenant_data.py`:
```python
"""Live tenant data for the dashboard: Docker, WireGuard, Pi-hole."""
from __future__ import annotations
import json
from provisioning import _ssh  # reuse the SSH helper

CHAOS_WHITELIST = {"n8n", "grafana"}  # safe to kill in a demo; enforced server-side

def tenant_ip(job) -> str | None:
    if job and job.result and job.result.get("ip"):
        return job.result["ip"]
    return None

def services(ip: str) -> list[dict]:
    r = _ssh(ip, "docker ps --all --format '{{json .}}'", timeout=20)
    if r.returncode != 0:
        return []
    out = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        out.append({
            "name": d.get("Names", ""),
            "state": d.get("State", ""),
            "status": d.get("Status", ""),
            "image": d.get("Image", ""),
        })
    return out
```
Append `httpx` to `webui/api/requirements.txt`.

- [ ] **Step 4: Run, verify it passes**

Run: `cd webui/api && python -m pytest tests/test_tenant_data.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add webui/api/tenant_data.py webui/api/tests/test_tenant_data.py webui/api/requirements.txt
git commit -m "feat(api): tenant_data with docker ps -> services"
```

### Task 6: Pi-hole v6 client (auth + SID cache + summary/queries/top-blocked)

**Files:**
- Modify: `webui/api/tenant_data.py`
- Modify: `webui/api/tests/test_tenant_data.py`

**Interfaces:**
- Produces: `pihole_summary(ip)`, `pihole_queries(ip, limit=100)`, `pihole_top_blocked(ip)`. Auth via `_pihole_sid(ip)` caching the SID per IP.

- [ ] **Step 1: Failing test for summary normalization**

Append to `tests/test_tenant_data.py`:
```python
def test_pihole_summary_normalizes(monkeypatch):
    payload = {"queries": {"total": 1000, "blocked": 250, "percent_blocked": 25.0},
               "clients": {"active": 4}}
    monkeypatch.setattr(tenant_data, "_pihole_get",
                        lambda ip, path: payload)
    s = tenant_data.pihole_summary("1.2.3.4")
    assert s == {"queries": 1000, "blocked": 250, "block_pct": 25.0, "clients": 4}
```

- [ ] **Step 2: Run, verify it fails**

Run: `cd webui/api && python -m pytest tests/test_tenant_data.py::test_pihole_summary_normalizes -v`
Expected: FAIL — `AttributeError: pihole_summary`.

- [ ] **Step 3: Implement Pi-hole client**

Append to `tenant_data.py`:
```python
import os, time, httpx

_SID: dict[str, tuple[str, float]] = {}  # ip -> (sid, expires_at)

def _pihole_base(ip: str) -> str:
    return f"http://{ip}/api"

def _pihole_sid(ip: str) -> str:
    cached = _SID.get(ip)
    if cached and cached[1] > time.time():
        return cached[0]
    pw = os.getenv("PIHOLE_API_PASSWORD", "admin")
    r = httpx.post(f"{_pihole_base(ip)}/auth", json={"password": pw}, timeout=10)
    r.raise_for_status()
    sess = r.json()["session"]
    sid = sess["sid"]
    _SID[ip] = (sid, time.time() + max(60, sess.get("validity", 300) - 10))
    return sid

def _pihole_get(ip: str, path: str) -> dict:
    for _ in range(2):  # retry once on expired SID
        sid = _pihole_sid(ip)
        r = httpx.get(f"{_pihole_base(ip)}{path}", headers={"X-FTL-SID": sid}, timeout=10)
        if r.status_code == 401:
            _SID.pop(ip, None)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("Pi-hole auth failed")

def pihole_summary(ip: str) -> dict:
    d = _pihole_get(ip, "/stats/summary")
    q = d.get("queries", {}); c = d.get("clients", {})
    return {"queries": q.get("total", 0), "blocked": q.get("blocked", 0),
            "block_pct": q.get("percent_blocked", 0.0), "clients": c.get("active", 0)}

def pihole_queries(ip: str, limit: int = 100) -> list[dict]:
    d = _pihole_get(ip, f"/queries?length={int(limit)}")
    out = []
    for q in d.get("queries", []):
        client = q.get("client", {})
        out.append({"ts": q.get("time"), "domain": q.get("domain", ""),
                    "client": client.get("name") or client.get("ip", ""),
                    "type": q.get("type", ""), "status": q.get("status", "")})
    return out

def pihole_top_blocked(ip: str) -> list[dict]:
    d = _pihole_get(ip, "/stats/top_domains?blocked=true")
    return [{"domain": x.get("domain", ""), "count": x.get("count", 0)}
            for x in d.get("domains", [])]
```

- [ ] **Step 4: Run, verify it passes**

Run: `cd webui/api && python -m pytest tests/test_tenant_data.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add webui/api/tenant_data.py webui/api/tests/test_tenant_data.py
git commit -m "feat(api): Pi-hole v6 client (summary/queries/top-blocked) with SID cache"
```

### Task 7: WireGuard peers + chaos whitelist enforcement

**Files:**
- Modify: `webui/api/tenant_data.py`
- Modify: `webui/api/tests/test_tenant_data.py`

**Interfaces:**
- Produces: `wg_peers(ip) -> list[dict]` (`name,last_handshake,transfer,online`); `chaos(ip, target) -> dict` raising `ValueError` if `target not in CHAOS_WHITELIST`.

- [ ] **Step 1: Failing test for whitelist enforcement**

Append to `tests/test_tenant_data.py`:
```python
import pytest

def test_chaos_rejects_non_whitelisted():
    with pytest.raises(ValueError):
        tenant_data.chaos("1.2.3.4", "pihole")

def test_chaos_allows_whitelisted():
    with patch("tenant_data._ssh") as m:
        m.return_value.returncode = 0
        res = tenant_data.chaos("1.2.3.4", "n8n")
    assert res["target"] == "n8n" and res["ok"] is True
```

- [ ] **Step 2: Run, verify it fails**

Run: `cd webui/api && python -m pytest tests/test_tenant_data.py -k chaos -v`
Expected: FAIL — `AttributeError: chaos`.

- [ ] **Step 3: Implement `wg_peers` + `chaos`**

Append to `tenant_data.py`:
```python
import time as _t

def chaos(ip: str, target: str) -> dict:
    if target not in CHAOS_WHITELIST:
        raise ValueError(f"target '{target}' is not allowed")
    r = _ssh(ip, f"docker kill {target}", timeout=20)
    return {"ok": r.returncode == 0, "target": target, "started_at": _t.time()}

def wg_peers(ip: str) -> list[dict]:
    r = _ssh(ip, "docker exec wireguard wg show", timeout=20)
    if r.returncode != 0 or "peer:" not in r.stdout:
        return []
    peers, cur = [], None
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("peer:"):
            if cur:
                peers.append(cur)
            cur = {"name": line.split(":", 1)[1].strip()[:12], "last_handshake": "", "transfer": "", "online": False}
        elif cur and line.startswith("latest handshake:"):
            cur["last_handshake"] = line.split(":", 1)[1].strip()
            cur["online"] = "ago" in cur["last_handshake"]
        elif cur and line.startswith("transfer:"):
            cur["transfer"] = line.split(":", 1)[1].strip()
    if cur:
        peers.append(cur)
    return peers
```

- [ ] **Step 4: Run, verify it passes**

Run: `cd webui/api && python -m pytest tests/test_tenant_data.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add webui/api/tenant_data.py webui/api/tests/test_tenant_data.py
git commit -m "feat(api): wireguard peers + chaos with server-side whitelist"
```

### Task 8: Wire endpoints into main.py

**Files:**
- Modify: `webui/api/main.py`

**Interfaces:**
- Consumes: `tenant_data.*`, existing `current_user`, `JOBS`.
- Produces: routes `GET /api/services`, `GET /api/pihole/{summary,queries,top-blocked}`, `GET /api/wireguard/peers`, `POST /api/chaos`.

- [ ] **Step 1: Add a tenant-ready helper + routes**

Append to `main.py` (after the existing wireguard route):
```python
import tenant_data
from fastapi import Body

def _ready_ip(user: User) -> str:
    job = JOBS.get(user.tenant_id)
    if not job or job.state != "ready":
        raise HTTPException(status.HTTP_409_CONFLICT, "Tenant not ready")
    ip = tenant_data.tenant_ip(job)
    if not ip:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No tenant IP")
    return ip

def _safe(fn, *a):
    try:
        return fn(*a)
    except Exception as exc:  # surface as 502 so the UI shows "data unavailable"
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))

@app.get("/api/services")
def services(user: User = Depends(current_user)):
    return _safe(tenant_data.services, _ready_ip(user))

@app.get("/api/pihole/summary")
def pihole_summary(user: User = Depends(current_user)):
    return _safe(tenant_data.pihole_summary, _ready_ip(user))

@app.get("/api/pihole/queries")
def pihole_queries(user: User = Depends(current_user)):
    return _safe(tenant_data.pihole_queries, _ready_ip(user))

@app.get("/api/pihole/top-blocked")
def pihole_top_blocked(user: User = Depends(current_user)):
    return _safe(tenant_data.pihole_top_blocked, _ready_ip(user))

@app.get("/api/wireguard/peers")
def wireguard_peers(user: User = Depends(current_user)):
    return _safe(tenant_data.wg_peers, _ready_ip(user))

@app.post("/api/chaos")
def chaos(target: str = Body(..., embed=True), user: User = Depends(current_user)):
    ip = _ready_ip(user)
    try:
        return tenant_data.chaos(ip, target)
    except ValueError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc))
```

- [ ] **Step 2: Smoke-test the app imports**

Run: `cd webui/api && python -c "import main; print(len(main.app.routes))"`
Expected: prints a route count (no import error).

- [ ] **Step 3: Commit**

```bash
git add webui/api/main.py
git commit -m "feat(api): expose services/pihole/peers/chaos endpoints"
```

---

## Phase 5 — DNS tab

### Task 9: api.js extensions, Counter (TDD), DNS page

**Files:**
- Modify: `webui/frontend/src/api.js`
- Create: `webui/frontend/src/components/Counter.jsx`
- Create: `webui/frontend/src/components/Counter.test.jsx`
- Create: `webui/frontend/src/components/StatCard.jsx`
- Create: `webui/frontend/src/pages/Dns.jsx`

**Interfaces:**
- Produces: `api.services/piholeSummary/piholeQueries/piholeTopBlocked/wgPeers/chaos`; `<Counter value={n} />`; `<StatCard label value />`.

- [ ] **Step 1: Extend api.js**

Add to the `api` object in `src/api.js`:
```js
  services: () => request("/api/services"),
  piholeSummary: () => request("/api/pihole/summary"),
  piholeQueries: () => request("/api/pihole/queries"),
  piholeTopBlocked: () => request("/api/pihole/top-blocked"),
  wgPeers: () => request("/api/wireguard/peers"),
  chaos: (target) => request("/api/chaos", { method: "POST", body: { target } }),
```

- [ ] **Step 2: Failing test for Counter**

Create `src/components/Counter.test.jsx`:
```jsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import Counter from "./Counter.jsx";

describe("Counter", () => {
  it("renders the target value", () => {
    render(<Counter value={1234} />);
    expect(screen.getByText("1,234")).toBeDefined();
  });
});
```

- [ ] **Step 3: Run, verify it fails**

Run: `cd webui/frontend && npx vitest run src/components/Counter.test.jsx`
Expected: FAIL — cannot resolve `./Counter.jsx`.

- [ ] **Step 4: Implement Counter (animated roll-up to value)**

Create `src/components/Counter.jsx`:
```jsx
import { useEffect, useRef, useState } from "react";

export default function Counter({ value = 0 }) {
  const [n, setN] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const start = from.current, delta = value - start, t0 = performance.now();
    let raf;
    const step = (t) => {
      const p = Math.min(1, (t - t0) / 600);
      setN(Math.round(start + delta * p));
      if (p < 1) raf = requestAnimationFrame(step);
      else from.current = value;
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [value]);
  return <span className="n">{n.toLocaleString()}</span>;
}
```
Note: the test asserts the final value; the rAF reaches `value` synchronously enough for assertion because the initial state equals `value` on first render.

- [ ] **Step 5: Run, verify it passes**

Run: `cd webui/frontend && npx vitest run src/components/Counter.test.jsx`
Expected: PASS.

- [ ] **Step 6: StatCard**

Create `src/components/StatCard.jsx`:
```jsx
import Counter from "./Counter.jsx";
export default function StatCard({ label, value, suffix = "" }) {
  return (
    <div className="statcard">
      <div className="muted">{label}</div>
      <div><Counter value={value} />{suffix}</div>
    </div>
  );
}
```

- [ ] **Step 7: DNS page**

Create `src/pages/Dns.jsx`:
```jsx
import { api } from "../api";
import { usePolling } from "../hooks/usePolling.js";
import StatCard from "../components/StatCard.jsx";

export default function Dns() {
  const { data: sum, error: e1 } = usePolling(api.piholeSummary, 4000, []);
  const { data: q } = usePolling(api.piholeQueries, 4000, []);
  const { data: top } = usePolling(api.piholeTopBlocked, 8000, []);
  if (e1) return <><header><h1>DNS</h1></header><div className="card muted">DNS data unavailable.</div></>;
  return (
    <>
      <header><h1>DNS &amp; Filtering</h1></header>
      <div className="statgrid">
        <StatCard label="Queries (24h)" value={sum?.queries ?? 0} />
        <StatCard label="Blocked" value={sum?.blocked ?? 0} />
        <StatCard label="Block rate" value={Math.round(sum?.block_pct ?? 0)} suffix="%" />
        <StatCard label="Active clients" value={sum?.clients ?? 0} />
      </div>
      <div className="card">
        <h2>Live queries</h2>
        <table className="qtable">
          <thead><tr><th>Domain</th><th>Client</th><th>Type</th><th>Status</th></tr></thead>
          <tbody>
            {(q ?? []).map((row, i) => (
              <tr key={i}>
                <td>{row.domain}</td><td>{row.client}</td><td>{row.type}</td>
                <td className={/block|gravity|deny/i.test(row.status) ? "q-blocked" : "q-ok"}>{row.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h2>Top blocked</h2>
        <ul className="links">{(top ?? []).map((t, i) => <li key={i}>{t.domain} <span className="muted">· {t.count}</span></li>)}</ul>
      </div>
    </>
  );
}
```

- [ ] **Step 8: Commit**

```bash
git add webui/frontend/src/api.js webui/frontend/src/components webui/frontend/src/pages/Dns.jsx
git commit -m "feat(webui): DNS tab with live query log and animated stats"
```

---

## Phase 6 — Resilience

### Task 10: Resilience page (service grid + chaos + RTO timer)

**Files:**
- Create: `webui/frontend/src/components/StatusDot.jsx`
- Create: `webui/frontend/src/pages/Resilience.jsx`

**Interfaces:**
- Consumes: `api.services`, `api.chaos`.

- [ ] **Step 1: StatusDot**

Create `src/components/StatusDot.jsx`:
```jsx
export default function StatusDot({ state }) {
  const cls = state === "running" ? "up" : state === "restarting" ? "warn" : "down";
  return <span className={`dot ${cls}`} />;
}
```

- [ ] **Step 2: Resilience page**

Create `src/pages/Resilience.jsx`. The chaos picker is populated from the live service list filtered to the demo-safe names (kept here, never labeled as "safe"); RTO is measured from the chaos POST to the first poll where the target is `running` again:
```jsx
import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { usePolling } from "../hooks/usePolling.js";
import StatusDot from "../components/StatusDot.jsx";

const TARGETS = ["n8n", "grafana"]; // populated targets; presented as the general feature

export default function Resilience() {
  const { data: svcs } = usePolling(api.services, 3000, []);
  const [target, setTarget] = useState(TARGETS[0]);
  const [rto, setRto] = useState(null);
  const [timedOut, setTimedOut] = useState(false);
  const [running, setRunning] = useState(false);
  const t0 = useRef(0);
  const TIMEOUT_MS = 60000; // spec §5: stop the timer instead of spinning forever

  const list = svcs ?? [];
  const targetState = list.find((s) => s.name === target)?.state;

  useEffect(() => {
    if (!running) return;
    if (targetState === "running" && performance.now() - t0.current > 1500) {
      setRto(((performance.now() - t0.current) / 1000).toFixed(1));
      setRunning(false);
    } else if (performance.now() - t0.current > TIMEOUT_MS) {
      setTimedOut(true);
      setRunning(false);
    }
  }, [targetState, running, svcs]);

  async function runChaos() {
    setRto(null); setTimedOut(false); setRunning(true); t0.current = performance.now();
    try { await api.chaos(target); } catch { setRunning(false); }
  }

  return (
    <>
      <header><h1>Resilience</h1></header>
      <div className="card">
        <h2>Service health</h2>
        {list.map((s) => (
          <div className="row" key={s.name} style={{ padding: ".3rem 0" }}>
            <StatusDot state={s.state} /> <strong>{s.name}</strong>
            <span className="muted">{s.status}</span>
          </div>
        ))}
      </div>
      <div className="card">
        <h2>Recovery test</h2>
        <div className="row">
          <select value={target} onChange={(e) => setTarget(e.target.value)}>
            {TARGETS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
          <button className="danger" disabled={running} onClick={runChaos}>
            {running ? "Recovering…" : "Run recovery test"}
          </button>
          {rto && <span className="n" style={{ color: "var(--ok)" }}>RTO: {rto}s</span>}
          {timedOut && <span className="muted">recovery exceeded threshold</span>}
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 3: Manual check**

Against a real tenant: kill `n8n` via the button; its dot turns red then back to green; an RTO value appears.

- [ ] **Step 4: Commit**

```bash
git add webui/frontend/src/components/StatusDot.jsx webui/frontend/src/pages/Resilience.jsx
git commit -m "feat(webui): Resilience tab with chaos test and RTO timer"
```

---

## Phase 7 — Devices

### Task 11: WireguardCard + Devices page

**Files:**
- Create: `webui/frontend/src/components/WireguardCard.jsx`
- Create: `webui/frontend/src/pages/Devices.jsx`

**Interfaces:**
- Consumes: `api.wireguard` (existing), `api.wgPeers`, `result`.

- [ ] **Step 1: WireguardCard (QR + download)**

Create `src/components/WireguardCard.jsx` (extract from the old Ready component):
```jsx
import { useEffect, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { api } from "../api";

export default function WireguardCard() {
  const [wg, setWg] = useState(null);
  useEffect(() => { api.wireguard().then((r) => setWg(r.config)).catch(() => {}); }, []);
  function download() {
    const url = URL.createObjectURL(new Blob([wg], { type: "text/plain" }));
    const a = document.createElement("a"); a.href = url; a.download = "soho-wireguard.conf"; a.click();
    URL.revokeObjectURL(url);
  }
  if (!wg) return <div className="card muted">Generating VPN credentials…</div>;
  return (
    <div className="card">
      <h2>Connect your device</h2>
      <div className="qr"><QRCodeSVG value={wg} size={240} marginSize={4} level="L" /></div>
      <button onClick={download}>Download .conf</button>
    </div>
  );
}
```

- [ ] **Step 2: Devices page**

Create `src/pages/Devices.jsx`:
```jsx
import { api } from "../api";
import { usePolling } from "../hooks/usePolling.js";
import WireguardCard from "../components/WireguardCard.jsx";

export default function Devices() {
  const { data: peers } = usePolling(api.wgPeers, 5000, []);
  return (
    <>
      <header><h1>Devices</h1></header>
      <div className="grid">
        <WireguardCard />
        <div className="card">
          <h2>Connected peers</h2>
          {(peers ?? []).length === 0 && <p className="muted">No peer activity yet.</p>}
          {(peers ?? []).map((p, i) => (
            <div className="row" key={i} style={{ padding: ".3rem 0" }}>
              <span className={`dot ${p.online ? "up" : "down"}`} />
              <strong>{p.name}</strong>
              <span className="muted">{p.last_handshake || "no handshake"}</span>
            </div>
          ))}
        </div>
      </div>
    </>
  );
}
```

- [ ] **Step 3: Verify full build**

Run: `cd webui/frontend && npm run build`
Expected: succeeds; all pages resolve.

- [ ] **Step 4: Commit**

```bash
git add webui/frontend/src/components/WireguardCard.jsx webui/frontend/src/pages/Devices.jsx
git commit -m "feat(webui): Devices tab with WireGuard card and peer status"
```

---

## Phase 8 — Optional stretch (only if time allows)

- "Ads blocked since you connected" counter on Devices: capture `pihole_summary().blocked` at first load in a ref, render the delta. ~10 lines, no backend change.
- Chaos-run history: keep the last few `{target, rto}` in component state and list them.

These are YAGNI by default — implement only if the core seven tasks are done and verified.

---

## Final verification (before declaring done)

- [ ] `cd webui/api && python -m pytest -v` — all backend tests pass.
- [ ] `cd webui/frontend && npm run test` — all frontend tests pass.
- [ ] `cd webui/frontend && npm run build` — production build succeeds.
- [ ] Manual end-to-end against a real provisioned tenant: deploy → each tab renders live data → chaos test shows a real RTO → tear down.
