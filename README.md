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

**VM2 stack:** Python 3.13 · Chainlit 2.x · LangGraph · langchain-mcp-adapters · Ollama  
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
- Python 3.13+
- [Ollama](https://ollama.com) installed and running at `http://localhost:11434`
- At least one supported model pulled in Ollama (see [Switching models](#switching-models))

---

## Quick start

```bash
# 1. Clone
git clone git@github.com:edmiand/5g-demo-app.git
cd 5g-demo-app

# 2. Create and activate virtualenv
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -e .

# 4. Copy environment file
cp .env.example .env
# .env is pre-configured for Ollama — no edits needed unless customising

# 5. Run the integration tests (optional but recommended)
python test_integration.py

# 6. Start the app
python start.py               # syncs branding then launches Chainlit
# or: python start.py --host 0.0.0.0 --port 8000
```

Open **http://\<VM2-IP\>:8000** in a browser.

---

## Configuration

### Model — `config/models.yaml`

```yaml
active: gemma4:31b-cloud   # ← change this line to switch models
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
# Edit config/models.yaml
active: qwen2.5:7b

# Make sure the model is pulled in Ollama
ollama pull qwen2.5:7b

# Restart Chainlit
chainlit run app.py --host 0.0.0.0 --port 8000
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
