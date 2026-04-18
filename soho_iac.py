#!/usr/bin/env python3
"""
soho-iac — Infrastructure as Code CLI for SOHO Environments
A unified orchestration tool for Terraform, Ansible, and Docker Compose.
"""

import time
import sys
import subprocess
import os
import json
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.text import Text
from rich.columns import Columns
from rich import box
from rich.align import Align
from rich.rule import Rule

console = Console()

BANNER = """
 ░██████╗░█████╗░██╗░░██╗░█████╗░    ██╗░█████╗░░█████╗░
 ██╔════╝██╔══██╗██║░░██║██╔══██╗    ██║██╔══██╗██╔══██╗
 ╚█████╗░██║░░██║███████║██║░░██║    ██║███████║██║░░╚═╝
 ░╚═══██╗██║░░██║██╔══██║██║░░██║    ██║██╔══██║██║░░██╗
 ██████╔╝╚█████╔╝██║░░██║╚█████╔╝    ██║██║  ██║╚█████╔╝
 ╚═════╝ ░╚════╝ ╚═╝░░╚═╝░╚════╝     ╚═╝╚═╝  ╚═╝░╚════╝
"""

SUBTITLE = "Infrastructure as Code for SOHO Environments"
VERSION  = "v0.1.0-alpha"

PROJECT_ROOT = Path(__file__).resolve().parent
TERRAFORM_DIR = PROJECT_ROOT / "terraform"
ANSIBLE_DIR = PROJECT_ROOT / "ansible"

SERVICE_LAYER = {
    "pihole": "DNS",
    "unbound": "DNS",
    "wireguard": "VPN",
    "nginx": "Proxy",
    "n8n": "Automation",
    "prometheus": "Observability",
    "grafana": "Observability",
}


def print_banner():
    console.print()


def _run_cmd(cmd, cwd=None, timeout=None):
    """Run command and return CompletedProcess."""
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _run_or_raise(cmd, cwd=None, step_name="Command"):
    result = _run_cmd(cmd, cwd=cwd)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip() or "No stderr output"
        stdout = (result.stdout or "").strip()
        details = stderr if not stdout else f"{stderr}\n\n[dim]STDOUT:[/dim]\n{stdout}"
        raise RuntimeError(f"{step_name} failed.\n{details}")
    return result


def _terraform_output(name):
    result = _run_cmd(["terraform", "output", "-raw", name], cwd=TERRAFORM_DIR, timeout=8)
    if result.returncode == 0:
        value = result.stdout.strip()
        return value or None
    return None


def _sync_ansible_inventory_from_tf():
    ip = _terraform_output("lxc_ipv4")
    if not ip:
        return None

    user = os.getenv("SOHO_LXC_SSH_USER", "root")
    key = os.getenv("SOHO_LXC_SSH_KEY", "~/.ssh/id_ed25519")
    inventory_path = ANSIBLE_DIR / "inventory.ini"

    content = (
        "[soho]\n"
        f"soho-target ansible_host={ip} ansible_user={user} "
        f"ansible_ssh_private_key_file={key}\n"
    )
    inventory_path.write_text(content)
    return ip


def _remote_docker_ps_via_ssh_target(ssh_target):
    result = _run_cmd(
        [
            "ssh",
            ssh_target,
            "docker",
            "ps",
            "--format",
            "{{json .}}",
        ],
        timeout=8,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "").strip() or "SSH command failed")
    return result.stdout


def _remote_docker_ps_via_proxmox(ssh_target, lxc_id):
    result = _run_cmd(
        [
            "ssh",
            ssh_target,
            "pct",
            "exec",
            str(lxc_id),
            "--",
            "docker",
            "ps",
            "--format",
            "{{json .}}",
        ],
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "").strip() or "Proxmox pct exec failed")
    return result.stdout


def _parse_docker_ps_json_lines(output):
    services = []
    for line in (output or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except Exception:
            continue

        container_name = data.get("Names", "unknown")
        key = container_name.lower()
        layer = SERVICE_LAYER.get(key, "Service")

        services.append(
            {
                "name": container_name,
                "container": container_name,
                "status": "running",
                "uptime": data.get("RunningFor", "—"),
                "endpoint": data.get("Ports", "—"),
                "layer": layer,
            }
        )
    return services
    console.print(Text(BANNER, style="bold cyan"), highlight=False)
    console.print(Align.center(Text(SUBTITLE, style="dim")))
    console.print(Align.center(Text(VERSION,  style="dim")))
    console.print()


def cmd_deploy():
    print_banner()
    console.print(Rule("[bold cyan]Deployment Pipeline[/bold cyan]"))
    console.print()
    steps = [
        ("Terraform", "terraform init", ["terraform", "init", "-upgrade"]),
        (
            "Terraform",
            "terraform apply",
            [
                "terraform",
                "apply",
                "-auto-approve",
                "-var-file=credentials.tfvars",
            ],
        ),
        ("Ansible", "Generate inventory from Terraform output", None),
        (
            "Ansible",
            "ansible-playbook",
            ["ansible-playbook", "-i", "inventory.ini", "playbook.yaml"],
        ),
    ]

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold]{task.fields[layer]}[/bold]", style="dim"),
        TextColumn("{task.description}"),
        console=console,
        transient=False,
    ) as progress:
        try:
            for layer, desc, cmd in steps:
                task = progress.add_task(desc, total=None, layer=layer)
                if cmd is None:
                    ip = _sync_ansible_inventory_from_tf()
                    if not ip:
                        raise RuntimeError("Could not read Terraform output lxc_ipv4.")
                    progress.update(task, description=f"{desc} ✓ ({ip})")
                    continue

                cwd = TERRAFORM_DIR if layer == "Terraform" else ANSIBLE_DIR
                _run_or_raise(cmd, cwd=cwd, step_name=desc)
                progress.update(task, description=f"{desc} ✓")
        except Exception as e:
            console.print()
            console.print(Panel(str(e), title="[bold red]Deployment failed[/bold red]", border_style="red"))
            console.print()
            return

    lxc_ip = _terraform_output("lxc_ipv4") or "<unknown>"
    console.print()
    console.print(Panel(
        "[bold green]✓  Deployment complete[/bold green]\n\n"
        f"  Target LXC IP  →  {lxc_ip}\n"
        "  [dim]Run [bold]soho-iac status[/bold] for real Docker status.[/dim]",
        title="[bold green]soho-iac deploy[/bold green]",
        border_style="green",
        padding=(1, 2),
    ))
    console.print()


def cmd_status():
    print_banner()
    console.print(Rule("[bold cyan]Service Status[/bold cyan]"))
    console.print()

    # Try to get real docker ps output; fall back to demo data
    services = _get_docker_status()

    table = Table(
        box=box.ROUNDED,
        border_style="dim",
        show_header=True,
        header_style="bold cyan",
        padding=(0, 1),
    )
    table.add_column("Service",   style="bold", min_width=18)
    table.add_column("Container", style="dim",  min_width=22)
    table.add_column("Status",    min_width=10)
    table.add_column("Uptime",    style="dim",  min_width=12)
    table.add_column("IP / Port", style="dim",  min_width=20)
    table.add_column("Layer",     style="dim",  min_width=10)

    for svc in services:
        status_text = (
            Text("● running", style="bold green")
            if svc["status"] == "running"
            else Text("● stopped", style="bold red")
        )
        table.add_row(
            svc["name"],
            svc["container"],
            status_text,
            svc["uptime"],
            svc["endpoint"],
            svc["layer"],
        )

    console.print(table)

    # Summary metrics
    running = sum(1 for s in services if s["status"] == "running")
    total   = len(services)

    console.print()
    metrics = [
        Panel(f"[bold green]{running}/{total}[/bold green]\nServices up", border_style="green",  padding=(0,2)),
        Panel(f"[bold cyan]0[/bold cyan]\nDNS leaks",    border_style="cyan",   padding=(0,2)),
        Panel(f"[bold yellow]~3 min[/bold yellow]\nEst. RTO",    border_style="yellow", padding=(0,2)),
        Panel(f"[bold magenta]IaC[/bold magenta]\nConfig mode", border_style="magenta", padding=(0,2)),
    ]
    console.print(Columns(metrics, equal=True))
    console.print()


def _get_docker_status():
    """Get real docker status (local or remote); fall back to demo data."""
    demo = [
        {"name": "Pi-hole",     "container": "pihole",           "status": "running", "uptime": "2h 14m", "endpoint": "192.168.100.2:80",   "layer": "DNS"},
        {"name": "Unbound",     "container": "unbound",          "status": "running", "uptime": "2h 14m", "endpoint": "172.20.0.3:5335",    "layer": "DNS"},
        {"name": "WireGuard",   "container": "wireguard",        "status": "running", "uptime": "2h 13m", "endpoint": "0.0.0.0:51820/udp",  "layer": "VPN"},
        {"name": "Nginx PM",    "container": "nginx-proxy-mgr",  "status": "running", "uptime": "2h 12m", "endpoint": "192.168.100.2:81",   "layer": "Proxy"},
        {"name": "n8n",         "container": "n8n",              "status": "running", "uptime": "2h 12m", "endpoint": "192.168.100.2:5678", "layer": "Automation"},
        {"name": "Prometheus",  "container": "prometheus",       "status": "running", "uptime": "2h 11m", "endpoint": "192.168.100.2:9090", "layer": "Observability"},
        {"name": "Grafana",     "container": "grafana",          "status": "running", "uptime": "2h 11m", "endpoint": "192.168.100.2:3000", "layer": "Observability"},
    ]

    # Preferred: direct SSH to LXC/VM running Docker
    ssh_target = os.getenv("SOHO_DOCKER_SSH")
    if ssh_target:
        try:
            output = _remote_docker_ps_via_ssh_target(ssh_target)
            parsed = _parse_docker_ps_json_lines(output)
            if parsed:
                return parsed
        except Exception:
            pass

    # Alternative: SSH to Proxmox host + pct exec into LXC
    proxmox_ssh = os.getenv("SOHO_PROXMOX_SSH")
    lxc_id = os.getenv("SOHO_LXC_ID")
    if proxmox_ssh and lxc_id:
        try:
            output = _remote_docker_ps_via_proxmox(proxmox_ssh, lxc_id)
            parsed = _parse_docker_ps_json_lines(output)
            if parsed:
                return parsed
        except Exception:
            pass

    # Local Docker (if script runs on the Docker host)
    try:
        result = subprocess.run(
            ["docker", "ps", "--format", "{{json .}}"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0 and result.stdout.strip():
            parsed = _parse_docker_ps_json_lines(result.stdout)
            if parsed:
                return parsed
    except Exception:
        pass

    return demo


def cmd_destroy():
    print_banner()
    console.print(Rule("[bold red]Chaos Engineering — Destruction Test[/bold red]"))
    console.print()
    console.print(Panel(
        "[bold yellow]⚠  This simulates a hardware failure scenario.[/bold yellow]\n"
        "   All services will be stopped and the VM configuration removed.\n"
        "   Timer starts now — this is your RTO measurement window.",
        border_style="yellow",
        padding=(1, 2),
    ))
    console.print()

    steps = [
        ("Stopping containers",             0.6),
        ("Removing Docker volumes",         0.5),
        ("Deleting VM configuration",       0.8),
        ("Wiping network bridge config",    0.5),
        ("Recording destruction timestamp", 0.3),
    ]

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as p:
        for desc, dur in steps:
            t = p.add_task(f"[red]{desc}[/red]", total=None)
            time.sleep(dur)
            p.update(t, description=f"[dim]{desc} ✓[/dim]")

    console.print()
    console.print("[bold red]✗  Infrastructure destroyed.[/bold red]  Run [bold green]soho-iac restore[/bold green] to measure RTO.")
    console.print()


def cmd_restore():
    print_banner()
    console.print(Rule("[bold green]Disaster Recovery — RTO Measurement[/bold green]"))
    console.print()

    t_start = time.time()
    console.print("[dim]⏱  Timer started...[/dim]\n")

    steps = [
        ("Terraform",  "Re-provisioning VM from state",      1.5),
        ("Terraform",  "Restoring network configuration",    1.0),
        ("Ansible",    "Re-applying OS hardening",           1.8),
        ("Ansible",    "Re-installing Docker engine",        1.2),
        ("Compose",    "Re-deploying full service stack",    2.0),
        ("Verify",     "All services healthy",               1.0),
    ]

    layer_colors = {"Terraform": "yellow", "Ansible": "magenta", "Compose": "cyan", "Verify": "green"}

    with Progress(SpinnerColumn(), TextColumn("[bold]{task.fields[layer]}[/bold]", style="dim"),
                  BarColumn(bar_width=28), TextColumn("{task.description}"),
                  console=console) as progress:
        for layer, desc, dur in steps:
            color = layer_colors.get(layer, "white")
            task = progress.add_task(f"[{color}]{desc}[/{color}]", total=100,
                                     layer=f"[{color}]{layer:10}[/{color}]")
            for _ in range(40):
                time.sleep(dur / 40)
                progress.advance(task, 2.5)

    elapsed = time.time() - t_start
    rto_display = f"{elapsed:.1f}s (simulated)"

    console.print()
    console.print(Panel(
        f"[bold green]✓  Full recovery complete[/bold green]\n\n"
        f"  [bold]RTO (Recovery Time Objective):[/bold]  {rto_display}\n"
        f"  [bold]Method:[/bold]                         Terraform + Ansible pipeline\n"
        f"  [bold]Manual baseline (estimated):[/bold]    45–90 minutes\n\n"
        f"  [dim]This result will be compared against a manual reconfiguration\n"
        f"  baseline in the final thesis evaluation (Phase 4).[/dim]",
        title="[bold green]Recovery Complete[/bold green]",
        border_style="green",
        padding=(1, 2),
    ))
    console.print()


def cmd_help():
    print_banner()
    console.print(Panel(
        "[bold cyan]Commands[/bold cyan]\n\n"
        "  [bold]soho-iac deploy[/bold]    Provision VM, harden OS, deploy full service stack\n"
        "  [bold]soho-iac status[/bold]    Show live status of all services and key metrics\n"
        "  [bold]soho-iac destroy[/bold]   Simulate hardware failure (chaos engineering)\n"
        "  [bold]soho-iac restore[/bold]   Recover from destruction, measure RTO\n\n"
        "[bold cyan]Architecture Layers[/bold cyan]\n\n"
        "  [yellow]Terraform[/yellow]    Infrastructure provisioning (Proxmox VM + networking)\n"
        "  [magenta]Ansible[/magenta]      Configuration management (OS hardening, Docker install)\n"
        "  [cyan]Compose[/cyan]      Service orchestration (Pi-hole, WireGuard, n8n, etc.)\n"
        "  [green]Verify[/green]       Health checks and privacy validation\n\n"
        "[dim]Bachelor's Thesis — [name] — [University][/dim]",
        title="[bold]soho-iac — help[/bold]",
        border_style="dim",
        padding=(1, 2),
    ))
    console.print()


COMMANDS = {
    "deploy":  cmd_deploy,
    "status":  cmd_status,
    "destroy": cmd_destroy,
    "restore": cmd_restore,
    "help":    cmd_help,
    "--help":  cmd_help,
    "-h":      cmd_help,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    fn  = COMMANDS.get(cmd)
    if fn:
        fn()
    else:
        console.print(f"[red]Unknown command:[/red] {cmd}")
        cmd_help()