const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

function token() {
  return localStorage.getItem("soho_token");
}

async function request(path, { method = "GET", body, auth = true } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (auth && token()) headers.Authorization = `Bearer ${token()}`;

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    // Stale token (e.g. the in-memory API was restarted): drop it and return
    // to the login screen instead of polling forever.
    if (res.status === 401 && auth && token()) {
      localStorage.removeItem("soho_token");
      window.location.reload();
    }
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch {
      /* non-JSON error */
    }
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  register: (email, password) =>
    request("/api/auth/register", { method: "POST", body: { email, password }, auth: false }),
  login: (email, password) =>
    request("/api/auth/login", { method: "POST", body: { email, password }, auth: false }),
  provision: () => request("/api/provision", { method: "POST" }),
  destroy: () => request("/api/provision", { method: "DELETE" }),
  status: () => request("/api/provision/status"),
  wireguard: () => request("/api/wireguard"),
  setToken: (t) => localStorage.setItem("soho_token", t),
  clearToken: () => localStorage.removeItem("soho_token"),
  hasToken: () => !!token(),
};
