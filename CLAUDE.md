# 5G Demo App — Claude Code Context

## What this project is
A Chainlit web application that acts as an agentic AI assistant for managing
a live Open5GS 5G core network. The AI agent uses LangGraph to autonomously
chain MCP tool calls, diagnose network issues, and take remediation actions.
All tool calls stream visibly as Steps in the Chainlit UI.

## Architecture
- VM1: Open5GS 5G core + MCP SSE server at :8080/sse (IP set in config/mcp.yaml)
- VM2 (this machine): Chainlit app + LangGraph + Ollama
- MCP connection: HTTP SSE — no local MCP process, just a URL
- LLM: Ollama at http://localhost:11434/v1 (active model set in config/models.yaml)

## Key paths
- config/models.yaml  — model selection (change 'active' to switch models)
- config/mcp.yaml     — MCP server URL (update VM1 IP on fresh deploy)
- agent/llm.py        — LangChain model loader (reads models.yaml)
- agent/mcp_bridge.py — SSE client (MultiServerMCPClient, reads mcp.yaml)
- agent/graph.py      — LangGraph ReAct agent
- app.py              — Chainlit entry point
- prompts/system.txt  — agent system prompt
- test_integration.py — 3-check integration test (LLM reachable · MCP tools · round-trip)

---

## Fresh Deploy — Step-by-Step

### 1. System prerequisites (Ubuntu 22.04+ ARM64 or x86-64)

```bash
sudo apt update && sudo apt install -y \
    python3 python3-venv python3-dev python3-pip \
    build-essential git curl
```

Node.js 20+ (needed for npm; mmdc is NOT used on ARM but npm is a system dep):
```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
```

### 2. Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
# Verify it's running:
systemctl status ollama
```

This project uses **cloud-routed models** — `ollama list` will show the model names
after first use. No `ollama pull` needed. Ollama is just the API gateway.

### 3. Clone the repo and create the venv

```bash
git clone <repo-url> 5g-demo-app
cd 5g-demo-app
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
```

### 4. Environment variables

```bash
cp .env.example .env   # content is identical — OLLAMA_API_KEY=ollama (dummy)
```

`.env` is committed and identical to `.env.example`. No secrets required — Ollama
does not validate the API key.

### 5. Configure VM1 MCP server URL

Edit `config/mcp.yaml` and set the correct IP for VM1:

```yaml
servers:
  open5gs:
    transport: sse
    url: http://<VM1-IP>:8080/sse
```

### 6. Bootstrap Chainlit config

On first run `start.py` writes branding into `.chainlit/config.toml`. If
`.chainlit/config.toml` exists but looks wrong, delete it and restart — Chainlit
regenerates it cleanly:

```bash
rm -f .chainlit/config.toml
./ctl.sh start          # start.py regenerates it then launches Chainlit
```

### 7. Start and verify

```bash
./ctl.sh start
# App is available at http://0.0.0.0:8000

# Optional: run the integration test
source .venv/bin/activate
python test_integration.py
# Checks: LLM reachable · MCP tools loaded · agent round-trip
```

### 8. Switching models

Edit `config/models.yaml`, change the `active` field, then restart:

```bash
./ctl.sh restart
```

Available models (all cloud-routed via Ollama):
- `gemma4:31b-cloud` — default, best quality
- `gpt-oss:20b-cloud` — alternative
- `qwen2.5:7b` — local fallback (~5 GB RAM)

### 9. Port / firewall

Chainlit listens on `0.0.0.0:8000`. If UFW is active:
```bash
sudo ufw allow 8000/tcp
```
Ollama (`localhost:11434`) is internal only — no firewall rule needed.

---

## MCP tools available on VM1
- nf_lifecycle          start/stop/restart/status any Open5GS NF
- system_health_snapshot one-shot health check of all NFs
- subscriber_crud        CRUD on subscriber profiles in MongoDB (supports filter param)
- list_ue_sessions       list active UE registrations and PDU sessions
- tail_nf_logs           filtered log reads from NF log files
- read_nf_config         read parsed YAML config for any NF
  - read_nf_config("amf")                    → full config (keys: logger, global, amf)
  - read_nf_config("amf", "amf.sbi.server.0") → subtree/index path
  - bad path → returns available sibling keys (explorable); bad NF → clear error

## Open5GS paths on VM1 (read-only reference)
- Logs:    /home/dmandrey/open5gs/install/var/log/open5gs/<nf>.log
- Configs: /home/dmandrey/open5gs/install/etc/open5gs/<nf>.yaml
- MongoDB: mongodb://localhost:27017  db: open5gs
- NF names: amf smf upf nrf udm udr ausf pcf bsf nssf

## Python environment
- Python 3.13, venv at .venv/
- Always use .venv/bin/python and .venv/bin/pip
- Install: pip install -e . (pyproject.toml, hatchling build system)
- Key deps: chainlit 2.11.1, langgraph 1.2.4, langchain-mcp-adapters 0.2.2, mcp 1.27.2,
            langchain-openai, httpx, pyyaml, python-dotenv

## Installed versions — API gotchas
- langgraph 1.2.x: create_react_agent uses `prompt=` not `state_modifier=`
- langchain-mcp-adapters 0.2.x: MultiServerMCPClient does NOT support async context manager;
  use: client = MultiServerMCPClient(servers); tools = await client.get_tools()
- Chainlit 2.x: @cl.set_starters only renders on a truly empty chat (no messages yet);
  for shortcuts accessible throughout a conversation, attach cl.Action buttons to messages
- Chainlit 2.x: adding elements to a streamed message via update() is silently dropped by
  the frontend — send elements in a fresh cl.Message instead
- Mermaid diagrams: rendered via mermaid.ink API (mmdc/Puppeteer fails on ARM — Chrome
  binary is x86-only); use cl.Image(content=bytes, size="large") in a separate message

## Constraints
- Chainlit 2.x is installed — use v2 API only, not v1 patterns
- Do NOT hand-write .chainlit/config.toml — delete it and let Chainlit regenerate it
- Do not modify anything on VM1
- Do not hardcode IPs or URLs — always read from config/mcp.yaml
- Do not hardcode model names — always read from config/models.yaml
- UPF operations on VM1 may require sudo — handle gracefully
- Tools return structured data (dicts/JSON), never raw strings

## Running the app
./ctl.sh start|stop|restart|status|logs   # always use ctl.sh — handles PID, child cleanup, nohup
# start.py syncs config/branding.yaml → .chainlit/config.toml before launching Chainlit on 0.0.0.0:8000

## Demo scenarios (3 action buttons on every message)
- Health Snapshot: calls system_health_snapshot, reports NF status table with emojis
- Watch Subscriber Attach: calls list_ue_sessions, shows registered UEs and PDU sessions
- Debug Attach Failure: calls system_health_snapshot to triage the network

## Agent behaviour (system prompt rules)
- Calls EXACTLY ONE tool per response — no autonomous chaining
- Never restarts/stops/starts a NF unless user explicitly asks
- Never suggests shell commands — uses MCP tools directly
- No preamble before tool calls ("let's call X" etc. is forbidden)
- Tool schema knowledge comes from MCP automatically — do not list tools in prompts/system.txt
- When trace tool returns call flow data, renders as Mermaid sequence diagram (sent as separate image message)
