# 5G Core Agent

An agentic AI assistant for managing a live **Open5GS 5G core network**.
Built with Chainlit, LangGraph, and MCP — the agent autonomously calls network
operations tools, diagnoses faults, and streams every step visibly in the UI.

---

## Architecture

```
┌─────────────────────────────┐        ┌──────────────────────────────────┐
│  VM2  (this machine)        │        │  VM1  (192.168.64.19)            │
│                             │        │                                  │
│  Chainlit UI  :8000         │        │  Open5GS 5G core (systemd)       │
│  LangGraph ReAct agent      │◄──SSE──│  MCP SSE server  :8080/sse       │
│  Ollama LLM   :11434        │        │  MongoDB         :27017          │
└─────────────────────────────┘        └──────────────────────────────────┘
```

**VM2 stack:** Python 3.11+ · Chainlit 2.x · LangGraph · langchain-mcp-adapters · Ollama  
**VM1 stack:** Open5GS · MCP SSE server exposing 5 network operations tools

---

## MCP Tools (live on VM1)

| Tool | What it does |
|------|-------------|
| `system_health_snapshot` | One-shot health check of all NFs, MongoDB, and TUN device |
| `nf_lifecycle` | Start / stop / restart / status any Open5GS NF |
| `tail_nf_logs` | Read and filter log entries from any NF log file |
| `list_ue_sessions` | List all active UE registrations and PDU sessions |
| `subscriber_crud` | Create / read / update / delete subscriber profiles in MongoDB |

---

## Prerequisites

### VM1 — must already be running
- Open5GS 5G core installed and started
- MCP SSE server running on port 8080 (`http://192.168.64.19:8080/sse`)

### VM2 — this machine
- Ubuntu 22.04 or 24.04 (other Debian-based distros should work)
- Python 3.11+ (see [System dependencies](#1-system-dependencies) below)
- [Ollama](https://ollama.com) installed and running at `http://localhost:11434`
- Network access to VM1 on port 8080
- Port 8000 open for inbound connections (Chainlit UI)

---

## Fresh VM Setup

Follow these steps in order on a clean Ubuntu VM. Each section is a
self-contained block of shell commands you can copy and run as-is.

### 1. System dependencies

```bash
sudo apt-get update
sudo apt-get install -y git curl build-essential

# Ubuntu 24.04 ships Python 3.12 — already satisfies >=3.11, skip the next block.
# Ubuntu 22.04 ships Python 3.10 — add deadsnakes PPA to get 3.11:
sudo apt-get install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install -y python3.11 python3.11-venv python3.11-dev
```

> **Ubuntu 24.04 users:** replace `python3.11` with `python3` in all commands
> below — the system Python is already 3.12.

### 2. Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh

# The installer registers and starts the ollama systemd service automatically.
# Verify it is running:
systemctl status ollama
```

### 3. Pull a model

`qwen2.5:7b` is the recommended starting model — small enough to run on a
4-vCPU / 8 GB VM and fast enough for interactive demos:

```bash
ollama pull qwen2.5:7b
```

Heavier models listed in `config/models.yaml` (`gemma4:31b-cloud`,
`gpt-oss:20b-cloud`) are available on specialised Ollama deployments and
require the matching model to be served at `localhost:11434`. Update
`config/models.yaml` → `active` to switch after pulling.

### 4. Open the firewall (if UFW is active)

```bash
# Allow inbound traffic to the Chainlit UI
sudo ufw allow 8000/tcp
sudo ufw status
```

### 5. Clone and install the app

```bash
# Clone
git clone git@github.com:edmiand/5g-demo-app.git
cd 5g-demo-app

# Create and activate virtualenv (adjust python3.11 → python3 on Ubuntu 24.04)
python3.11 -m venv .venv
source .venv/bin/activate

# Install all Python dependencies
pip install --upgrade pip
pip install -e .

# Copy environment file
cp .env.example .env
# .env is pre-configured for Ollama — no edits needed unless customising
```

### 6. Point the app at your VM1

Edit `config/mcp.yaml` and set the correct IP/port for your VM1:

```yaml
servers:
  open5gs:
    transport: sse
    url: http://<VM1-IP>:8080/sse   # ← replace with your VM1 address
```

### 7. Set the active model

Edit `config/models.yaml` and set `active` to the model you pulled:

```yaml
active: qwen2.5:7b
```

### 8. Run the integration tests (optional but recommended)

```bash
source .venv/bin/activate
python test_integration.py
# Exit code 0 = LLM reachable · MCP tools loaded · agent round-trip OK
```

### 9. Start the app

```bash
source .venv/bin/activate
python start.py                    # binds to 0.0.0.0:8000 by default
# or: python start.py --host 0.0.0.0 --port 8000
```

Open **http://\<VM2-IP\>:8000** in a browser.

---

## Run as a systemd service (persistent)

Create `/etc/systemd/system/5g-demo-app.service` — adjust `User`, `WorkingDirectory`,
and the Python path to match your setup:

```ini
[Unit]
Description=5G Core Agent (Chainlit)
After=network.target ollama.service

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/5g-demo-app
ExecStart=/home/ubuntu/5g-demo-app/.venv/bin/python start.py --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now 5g-demo-app
sudo systemctl status 5g-demo-app
```

---

## Quick start (existing VM)

If the VM already has Python 3.11+, Ollama, and a model pulled:

```bash
git clone git@github.com:edmiand/5g-demo-app.git
cd 5g-demo-app
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# Edit config/mcp.yaml → set VM1 address
# Edit config/models.yaml → set active model
python start.py
```

---

## Configuration

### Model — `config/models.yaml`

```yaml
active: qwen2.5:7b   # ← change this line to switch models
```

Available entries: `gemma4:31b-cloud`, `gpt-oss:20b-cloud`, `qwen2.5:7b`.  
Add a new block under `models:` to register any other Ollama model.  
Restart Chainlit after changing.

### MCP server — `config/mcp.yaml`

```yaml
servers:
  open5gs:
    transport: sse
    url: http://192.168.64.19:8080/sse  # ← VM1 address
```

---

## Project layout

```
app.py                  # Chainlit entry point — chat lifecycle + streaming
agent/
  llm.py               # LangChain model loader (reads config/models.yaml)
  mcp_bridge.py        # SSE client via MultiServerMCPClient
  graph.py             # LangGraph ReAct agent (create_react_agent)
config/
  models.yaml          # Model registry and active model selection
  mcp.yaml             # MCP server URL
prompts/
  system.txt           # Agent system prompt — behaviour rules and formatting
.env.example           # Environment template (copy to .env)
test_integration.py    # 3-check integration test (LLM · MCP · agent round-trip)
```

---

## Branding

Edit `config/branding.yaml` — all three values are applied automatically on next start:

```yaml
agent_name: "5G Core Agent"      # Chainlit header name
welcome_title: "5G Core Agent ready"  # bold heading in first chat message
logo_file: rogers-logo.svg        # file must exist in public/logos/
```

## Demo scenarios

Three quick-start buttons appear in the UI on every chat start:

1. **🏥 Health Snapshot** — calls `system_health_snapshot`, reports NF status table with 🟢🟡🔴 emojis
2. **👀 Watch Subscriber Attach** — calls `list_ue_sessions`, shows all registered UEs and PDU sessions
3. **🔍 Debug Attach Failure** — calls `system_health_snapshot` to triage the network before deeper investigation

You can also type free-form questions, e.g.:
- `show subscriber imsi-999700000000001`
- `tail amf logs for the last 10 minutes`
- `restart the smf`

---

## Switching models

```bash
# Pull the model in Ollama first
ollama pull qwen2.5:7b

# Edit config/models.yaml
active: qwen2.5:7b

# Restart the app
python start.py
```

---

## Running tests

```bash
source .venv/bin/activate
python test_integration.py
```

Tests check: LLM reachability · MCP tool loading (expects 5 tools) · agent round-trip invocation.  
Exit code 0 = all pass.

---

## Known constraints

- **Chainlit 2.x API** — do not use v1 patterns (`@cl.langchain_factory`, etc.)
- **`.chainlit/config.toml`** — delete and let Chainlit regenerate if you see *"config file is outdated"*
- **UPF operations** on VM1 may require `sudo` — the MCP server handles privilege escalation
- **Ollama API key** is set to the literal string `ollama` — this is correct, Ollama does not validate it
