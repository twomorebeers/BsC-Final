import { useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { api } from "./api";

export default function App() {
  const [authed, setAuthed] = useState(api.hasToken());
  if (!authed) return <Auth onAuthed={() => setAuthed(true)} />;
  return <Dashboard onLogout={() => { api.clearToken(); setAuthed(false); }} />;
}

function Auth({ onAuthed }) {
  const [mode, setMode] = useState("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const fn = mode === "register" ? api.register : api.login;
      const { token } = await fn(email, password);
      api.setToken(token);
      onAuthed();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="center">
      <form className="card auth" onSubmit={submit}>
        <h1>SOHO‑IaC</h1>
        <p className="muted">Your private network security stack, deployed in minutes.</p>
        <input type="email" placeholder="Email" value={email} required
               onChange={(e) => setEmail(e.target.value)} />
        <input type="password" placeholder="Password" value={password} required
               onChange={(e) => setPassword(e.target.value)} />
        {error && <div className="error">{error}</div>}
        <button disabled={busy}>
          {busy ? "…" : mode === "register" ? "Create account" : "Sign in"}
        </button>
        <button type="button" className="link"
                onClick={() => setMode(mode === "register" ? "login" : "register")}>
          {mode === "register" ? "Already have an account? Sign in" : "New here? Create an account"}
        </button>
      </form>
    </div>
  );
}

function Dashboard({ onLogout }) {
  const [status, setStatus] = useState({ state: "idle", logs: [] });
  const [wg, setWg] = useState(null);
  const logRef = useRef(null);

  // Poll while a job is running.
  useEffect(() => {
    let active = true;
    async function tick() {
      try {
        const s = await api.status();
        if (active) setStatus(s);
      } catch { /* ignore transient errors */ }
    }
    tick();
    const id = setInterval(tick, 2000);
    return () => { active = false; clearInterval(id); };
  }, []);

  // Fetch WireGuard config once the stack is ready.
  useEffect(() => {
    if (status.state === "ready" && !wg) {
      api.wireguard().then((r) => setWg(r.config)).catch(() => {});
    }
    if (status.state === "idle") setWg(null);
  }, [status.state, wg]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [status.logs]);

  const busy = status.state === "provisioning" || status.state === "destroying";

  return (
    <div className="page">
      <header>
        <strong>SOHO‑IaC</strong>
        <button className="link" onClick={onLogout}>Sign out</button>
      </header>

      <div className="card">
        <div className="row">
          <StateBadge state={status.state} />
          <div className="spacer" />
          {(status.state === "idle") && (
            <button onClick={() => api.provision().then(setStatus)}>Deploy my network</button>
          )}
          {(status.state === "ready" || status.state === "error") && (
            <button className="danger" onClick={() => api.destroy().then(setStatus)}>
              Tear down
            </button>
          )}
          {busy && <button disabled>Working…</button>}
        </div>

        {status.error && <div className="error">{status.error}</div>}

        {(busy || status.logs.length > 0) && (
          <pre className="logs" ref={logRef}>
            {status.logs.join("\n")}
          </pre>
        )}
      </div>

      {status.state === "ready" && status.result && (
        <Ready result={status.result} wg={wg} />
      )}
    </div>
  );
}

function Ready({ result, wg }) {
  const grafana = `${result.grafana_url}/d/soho-overview?orgId=1&kiosk&theme=light`;

  function downloadConfig() {
    const blob = new Blob([wg], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "soho-wireguard.conf";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <>
      <div className="grid">
        <div className="card">
          <h2>Connect your device</h2>
          <p className="muted">
            Install WireGuard (any OS), then scan this QR on mobile or import the
            config file on desktop.
          </p>
          {wg ? (
            <>
              <div className="qr"><QRCodeSVG value={wg} size={264} marginSize={4} level="L" /></div>
              <button onClick={downloadConfig}>Download .conf</button>
            </>
          ) : (
            <p className="muted">Generating your VPN credentials…</p>
          )}
        </div>

        <div className="card">
          <h2>Your services</h2>
          <ul className="links">
            <li><a href={result.pihole_url} target="_blank" rel="noreferrer">Pi‑hole admin</a></li>
            <li><a href={result.grafana_url} target="_blank" rel="noreferrer">Grafana</a></li>
            <li className="muted">Server IP: {result.ip}</li>
          </ul>
        </div>
      </div>

      <div className="card">
        <h2>Network activity</h2>
        <iframe className="grafana" src={grafana} title="Grafana dashboard" />
      </div>
    </>
  );
}

function StateBadge({ state }) {
  const label = {
    idle: "Not deployed",
    provisioning: "Deploying…",
    ready: "● Online",
    destroying: "Tearing down…",
    error: "Error",
  }[state] || state;
  return <span className={`badge ${state}`}>{label}</span>;
}
