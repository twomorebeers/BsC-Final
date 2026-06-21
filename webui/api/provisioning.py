"""
Tenant provisioning — the SaaS control-plane logic.

Each registered user gets an isolated Terraform *workspace*, so their state
never collides with another tenant's. Provisioning:

    register -> terraform apply (1 Hetzner VM) -> ansible deploy stack
             -> fetch WireGuard peer config -> hand back to user

Hetzner bills hourly, so `destroy_tenant` tears the VM down when the session
ends and the tenant's monthly cost stays near zero.

Requires on the control-plane host:
  - terraform, ansible-playbook, ssh on PATH
  - HCLOUD_TOKEN env var (Hetzner Cloud API token)
  - SSH key matching terraform var ssh_public_key_path (default
    ~/.ssh/id_ed25519.pub), used by Ansible to reach the new VM
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path
from typing import Callable, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TERRAFORM_DIR = PROJECT_ROOT / "terraform"
ANSIBLE_DIR = PROJECT_ROOT / "ansible"

# Where Ansible syncs the docker stack and where linuxserver/wireguard writes
# the generated peer config (peer1) inside the synced tree.
REMOTE_PROJECT_DIR = "/opt/thesis-project"
WG_PEER_CONF = f"{REMOTE_PROJECT_DIR}/config/wireguard/peer1/peer1.conf"

LogFn = Optional[Callable[[str], None]]


class ProvisioningError(RuntimeError):
    pass


def slugify(tenant_id: str) -> str:
    """Terraform workspace + Hetzner resource names: lowercase, alnum + dashes."""
    slug = re.sub(r"[^a-z0-9-]+", "-", tenant_id.strip().lower()).strip("-")
    if not slug:
        raise ProvisioningError(f"tenant_id '{tenant_id}' produced an empty slug")
    return slug[:48]


def _tf_env() -> dict:
    token = os.getenv("HCLOUD_TOKEN")
    if not token:
        raise ProvisioningError("HCLOUD_TOKEN is not set on the control plane")
    return {
        **os.environ,
        "TF_VAR_hcloud_token": token,
        "TF_IN_AUTOMATION": "1",
        "TF_INPUT": "0",
    }


def _run(cmd, cwd, env=None, timeout=None, log: LogFn = None) -> str:
    """Run a command, streaming combined output to `log`. Raise on non-zero."""
    if log:
        log(f"$ {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    lines: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        lines.append(line)
        if log:
            log(line)
    proc.wait(timeout=timeout)
    output = "\n".join(lines)
    if proc.returncode != 0:
        raise ProvisioningError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n{output[-2000:]}"
        )
    return output


def _select_workspace(slug: str, env: dict, log: LogFn = None) -> None:
    # -or-create is supported on Terraform >= 1.4 (project requires >= 1.5).
    _run(
        ["terraform", "workspace", "select", "-or-create", slug],
        cwd=TERRAFORM_DIR,
        env=env,
        timeout=30,
        log=log,
    )


def _tf_output(name: str, env: dict) -> str:
    proc = subprocess.run(
        ["terraform", "output", "-raw", name],
        cwd=str(TERRAFORM_DIR),
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _write_inventory(ip: str) -> None:
    user = os.getenv("SOHO_SSH_USER", "root")
    key = os.getenv("SOHO_SSH_KEY", "~/.ssh/id_ed25519")
    (ANSIBLE_DIR / "inventory.ini").write_text(
        "[soho]\n"
        f"soho-target ansible_host={ip} ansible_user={user} "
        f"ansible_ssh_private_key_file={key} "
        "ansible_ssh_common_args='-o StrictHostKeyChecking=no "
        "-o UserKnownHostsFile=/dev/null "
        "-o GlobalKnownHostsFile=/dev/null'\n"
    )


def _ssh(ip: str, remote_cmd: str, timeout: int = 20) -> subprocess.CompletedProcess:
    user = os.getenv("SOHO_SSH_USER", "root")
    key = os.path.expanduser(os.getenv("SOHO_SSH_KEY", "~/.ssh/id_ed25519"))
    return subprocess.run(
        [
            "ssh",
            "-i", key,
            "-o", "IdentitiesOnly=yes",
            # Ephemeral VMs recycle IPs, so never track/verify host keys —
            # otherwise a reused IP with a new key blocks the connection.
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "ConnectTimeout=10",
            "-o", "LogLevel=ERROR",
            f"{user}@{ip}",
            remote_cmd,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _wait_for_ssh(ip: str, log: LogFn = None) -> None:
    """Block until the new VM accepts SSH and cloud-init has finished.

    Terraform returns as soon as Hetzner reports the server created, but the OS
    may still be booting / running cloud-init (installing packages + injecting
    our key). Running Ansible too early causes UNREACHABLE / tmp-dir failures.
    """
    for attempt in range(30):  # ~5 min max
        if _ssh(ip, "true", timeout=15).returncode == 0:
            break
        if log:
            log(f"Waiting for SSH on {ip} (attempt {attempt + 1}/30)...")
        time.sleep(10)
    else:
        raise ProvisioningError(f"Timed out waiting for SSH on {ip}")

    if log:
        log("SSH up; waiting for cloud-init to finish...")
    # cloud-init status --wait blocks until first-boot setup is complete.
    _ssh(ip, "cloud-init status --wait >/dev/null 2>&1 || true", timeout=300)
    if log:
        log("VM ready.")


def _fetch_wireguard_config(ip: str, log: LogFn = None) -> str:
    """Read the generated WireGuard peer config off the freshly deployed VM.

    The linuxserver/wireguard container generates peer configs a few seconds
    after start, so retry briefly.
    """
    import time

    for attempt in range(12):
        result = _ssh(ip, f"cat {WG_PEER_CONF} 2>/dev/null || true")
        if result.returncode == 0 and "[Interface]" in result.stdout:
            return result.stdout.strip()
        if log:
            log(f"WireGuard config not ready yet (attempt {attempt + 1}/12)...")
        time.sleep(5)
    raise ProvisioningError("Timed out waiting for WireGuard peer config")


def provision_tenant(tenant_id: str, log: LogFn = None) -> dict:
    """Provision an isolated stack for a tenant. Returns connection details."""
    slug = slugify(tenant_id)
    env = _tf_env()
    tf_vars = ["-var", f"tenant_id={slug}"]

    _run(["terraform", "init", "-input=false"], cwd=TERRAFORM_DIR, env=env, timeout=180, log=log)
    _select_workspace(slug, env, log=log)
    _run(
        ["terraform", "apply", "-auto-approve", "-input=false", *tf_vars],
        cwd=TERRAFORM_DIR, env=env, timeout=600, log=log,
    )

    ip = _tf_output("server_ipv4", env)
    if not ip:
        raise ProvisioningError("Terraform did not return an IP for the new VM")
    if log:
        log(f"VM provisioned at {ip}")

    _wait_for_ssh(ip, log=log)

    _write_inventory(ip)
    ansible_env = {**os.environ, "ANSIBLE_HOST_KEY_CHECKING": "False"}
    _run(
        ["ansible-playbook", "-i", "inventory.ini", "playbook.yaml"],
        cwd=ANSIBLE_DIR, env=ansible_env, timeout=900, log=log,
    )

    wg_config = _fetch_wireguard_config(ip, log=log)

    return {
        "tenant_id": slug,
        "ip": ip,
        "wireguard_config": wg_config,
        "grafana_url": f"http://{ip}:3000",
        "pihole_url": f"http://{ip}/admin",
    }


def destroy_tenant(tenant_id: str, log: LogFn = None) -> None:
    """Tear down a tenant's VM and remove its workspace."""
    slug = slugify(tenant_id)
    env = _tf_env()
    _select_workspace(slug, env, log=log)
    _run(
        ["terraform", "destroy", "-auto-approve", "-input=false",
         "-var", f"tenant_id={slug}"],
        cwd=TERRAFORM_DIR, env=env, timeout=600, log=log,
    )
    # Workspaces can't be deleted while selected.
    _run(["terraform", "workspace", "select", "default"], cwd=TERRAFORM_DIR, env=env, timeout=30, log=log)
    _run(["terraform", "workspace", "delete", "-force", slug], cwd=TERRAFORM_DIR, env=env, timeout=30, log=log)


def tenant_ip(tenant_id: str) -> str:
    """Return the current IP for a tenant (empty string if not provisioned)."""
    slug = slugify(tenant_id)
    env = _tf_env()
    try:
        _select_workspace(slug, env)
        return _tf_output("server_ipv4", env)
    except ProvisioningError:
        return ""
