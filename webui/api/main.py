"""
SOHO-IaC control plane — FastAPI.

Thin SaaS wrapper around the per-tenant provisioning module:
  register/login -> provision (background) -> poll status/logs -> get WireGuard
  config / embed Grafana -> destroy.

NOTE (thesis scope): auth + state are intentionally minimal and in-memory.
Users and provisioning jobs are lost on restart. For a graded demo this is
fine; production would swap these for a database + real session management.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import threading
from dataclasses import dataclass, field
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr

import provisioning

app = FastAPI(title="SOHO-IaC Control Plane", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("WEBUI_CORS_ORIGINS", "http://localhost:5173").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

bearer = HTTPBearer(auto_error=True)


# --------------------------------------------------------------------------- #
# In-memory state
# --------------------------------------------------------------------------- #
@dataclass
class Job:
    """Tracks one provision/destroy run for a tenant."""
    state: str = "idle"  # idle | provisioning | ready | destroying | error
    logs: list[str] = field(default_factory=list)
    result: Optional[dict] = None
    error: Optional[str] = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def log(self, line: str) -> None:
        with self.lock:
            self.logs.append(line)


@dataclass
class User:
    email: str
    pw_hash: str
    salt: str
    tenant_id: str


USERS: dict[str, User] = {}          # email -> User
TOKENS: dict[str, str] = {}          # token -> email
JOBS: dict[str, Job] = {}            # tenant_id -> Job


def _hash_pw(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()


def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> User:
    email = TOKENS.get(creds.credentials)
    if not email or email not in USERS:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return USERS[email]


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #
class Credentials(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    token: str
    tenant_id: str


class StatusResponse(BaseModel):
    state: str
    logs: list[str]
    result: Optional[dict] = None
    error: Optional[str] = None


# --------------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------------- #
@app.post("/api/auth/register", response_model=TokenResponse)
def register(body: Credentials):
    if body.email in USERS:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    salt = secrets.token_hex(16)
    tenant_id = provisioning.slugify(body.email.split("@")[0] + "-" + secrets.token_hex(3))
    USERS[body.email] = User(
        email=body.email,
        pw_hash=_hash_pw(body.password, salt),
        salt=salt,
        tenant_id=tenant_id,
    )
    token = secrets.token_urlsafe(32)
    TOKENS[token] = body.email
    return TokenResponse(token=token, tenant_id=tenant_id)


@app.post("/api/auth/login", response_model=TokenResponse)
def login(body: Credentials):
    user = USERS.get(body.email)
    if not user or _hash_pw(body.password, user.salt) != user.pw_hash:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    token = secrets.token_urlsafe(32)
    TOKENS[token] = body.email
    return TokenResponse(token=token, tenant_id=user.tenant_id)


# --------------------------------------------------------------------------- #
# Provisioning
# --------------------------------------------------------------------------- #
def _provision_worker(tenant_id: str, job: Job) -> None:
    try:
        result = provisioning.provision_tenant(tenant_id, log=job.log)
        with job.lock:
            job.result = result
            job.state = "ready"
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        with job.lock:
            job.error = str(exc)
            job.state = "error"
        job.log(f"ERROR: {exc}")


def _destroy_worker(tenant_id: str, job: Job) -> None:
    try:
        provisioning.destroy_tenant(tenant_id, log=job.log)
        with job.lock:
            job.result = None
            job.state = "idle"
    except Exception as exc:  # noqa: BLE001
        with job.lock:
            job.error = str(exc)
            job.state = "error"
        job.log(f"ERROR: {exc}")


@app.post("/api/provision", response_model=StatusResponse)
def provision(user: User = Depends(current_user)):
    job = JOBS.get(user.tenant_id)
    if job and job.state in ("provisioning", "destroying"):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Already {job.state}")
    job = Job(state="provisioning")
    JOBS[user.tenant_id] = job
    job.log(f"Starting provisioning for tenant {user.tenant_id}...")
    threading.Thread(target=_provision_worker, args=(user.tenant_id, job), daemon=True).start()
    return _status_of(job)


@app.delete("/api/provision", response_model=StatusResponse)
def destroy(user: User = Depends(current_user)):
    job = JOBS.get(user.tenant_id)
    if not job or job.state not in ("ready", "error"):
        raise HTTPException(status.HTTP_409_CONFLICT, "Nothing to destroy")
    job.state = "destroying"
    job.log(f"Destroying tenant {user.tenant_id}...")
    threading.Thread(target=_destroy_worker, args=(user.tenant_id, job), daemon=True).start()
    return _status_of(job)


@app.get("/api/provision/status", response_model=StatusResponse)
def provision_status(user: User = Depends(current_user)):
    job = JOBS.get(user.tenant_id)
    if not job:
        return StatusResponse(state="idle", logs=[])
    return _status_of(job)


def _status_of(job: Job) -> StatusResponse:
    with job.lock:
        return StatusResponse(
            state=job.state,
            logs=list(job.logs),
            result=job.result,
            error=job.error,
        )


@app.get("/api/wireguard")
def wireguard(user: User = Depends(current_user)):
    job = JOBS.get(user.tenant_id)
    if not job or not job.result or "wireguard_config" not in job.result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No WireGuard config available")
    return {"config": job.result["wireguard_config"]}


@app.get("/api/health")
def health():
    return {"status": "ok"}
