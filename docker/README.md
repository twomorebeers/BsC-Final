# Thesis Project: Infrastructure as Code & Network Resilience (Demo Version)

**Student:** Bogdan Rutas  
**Adviser:** Ioan Dragan  
**Project Title:** Evaluating the Efficacy of Infrastructure as Code in SOHO Environments  

---

## 1. Overview
This repository contains the practical implementation of the thesis. While the production environment is provisioned via **Terraform** on a **Hetzner Cloud** VM (on demand, per tenant), this specific configuration is a **Portable Demo Artifact**. 

It has been adapted to run on **Docker Desktop** (Windows/macOS/Linux) to facilitate evaluation without requiring a dedicated hypervisor.

### Key Differences in Demo Mode
* **Networking:** Uses `bridge` mode instead of `host` mode to ensure compatibility with Windows/Mac networking stacks.
* **Ports:** Standard ports (DNS `53`, HTTP `80`) are remapped to high-range ports (e.g., `5353`, `8000`) to prevent conflicts with the host operating system.
* **WireGuard:** Runs in userspace mode (`WIREGUARD_GO=true`) to avoid kernel dependency issues on non-Linux hosts.

---

## 2. Prerequisites
* **Docker Desktop** (Installed and running)
* **Git** (Optional, if cloning the repo)

---

## 3. Quick Start Guide
Follow these steps to deploy the application stack locally.

1.  **Navigate to the docker directory:**
    Open your terminal or command prompt and enter the folder containing the project files.
    ```bash
    cd path/to/thesis-project/docker
    ```

2.  **Launch the Stack:**
    Run the following command to start the services using the demo configuration file.
    ```bash
    docker compose -f docker-compose.demo.yml up -d
    ```

3.  **Verify Status:**
    Ensure all containers are running:
    ```bash
    docker compose -f docker-compose.demo.yml ps
    ```

---

## 4. Service Access & Credentials
Once the stack is running, you can access the services via the following URLs:

| Service | Function | URL | Username | Password |
| :--- | :--- | :--- | :--- | :--- |
| **Pi-hole** | DNS Filter / Ad Block | `http://localhost:8080/admin` | N/A | `admin` |
| **Nginx Proxy** | Reverse Proxy Manager | `http://localhost:8181` | `admin@example.com` | `changeme` |
| **n8n** | Workflow Automation | `http://localhost:5678` | `admin` | `thesis_demo` |
| **Unbound** | Recursive Resolver | *(Backend Service Only)* | N/A | N/A |

**Where to find the Pi-hole password:**  
It’s set via the `WEBPASSWORD` environment variable in the compose file you used:
- Demo stack: `/Users/bogdishor/Desktop/LICENTA/docker/docker-compose-demo.yml` (`WEBPASSWORD=admin`)
- Full stack: `/Users/bogdishor/Desktop/LICENTA/docker/docker-compose.yml` (`WEBPASSWORD=admin`)

---

## 5. Testing the Logic
To verify the stack is functioning as intended:

1.  **Test DNS Resolution:**
    You can force a DNS query through the containerized stack (mapped to port 5353):
    ```bash
    # On Windows (Command Prompt)
    nslookup -P 5353 google.com 127.0.0.1
    
    # On macOS/Linux
    dig @127.0.0.1 -p 5353 google.com
    ```
    *Result:* You should see a successful answer. Check the Pi-hole Query Log to see the request appear.

2.  **Test Ad Blocking:**
    Query a known ad domain:
    ```bash
    nslookup -P 5353 doubleclick.net 127.0.0.1
    ```
    *Result:* The query should return `0.0.0.0`, confirming the block list is active.

---

## 6. Shutdown
To stop the project and clean up resources:

```bash
docker compose -f docker-compose.demo.yml down
```

---

## 7. 5‑Minute Live Presentation Outline (Required Structure)
**Total time: 5 minutes**

1. **Brief context & problem (0:00–1:00)**
   - One‑sentence thesis goal.
   - The SOHO pain point (manual setup, inconsistent configs, weak resilience).

2. **Personal contributions (1:00–2:00)**
   - IaC design choices (Ansible + Docker + Terraform scope).
   - Custom networking/DNS stack (Pi‑hole + Unbound).
   - Demo adaptation for portability (bridge mode, port remaps).

3. **Application demo or results (2:00–4:00)**
   - Show running containers (`docker compose ... ps`).
   - DNS test: `dig @127.0.0.1 -p 5353 google.com`.
   - Ad‑block test: `nslookup -P 5353 doubleclick.net 127.0.0.1`.
   - Mention observed metrics (latency, cache hits) if available.

4. **Planned tasks for semester 2 (4:00–5:00)**
   - Terraform VM provisioning on Hetzner Cloud.
   - Hardening & monitoring (logging, alerting).
   - Evaluation: compare baseline vs IaC (time, errors, resilience).

**Submission note:** Keep slides to ~4–5 and practice timing.