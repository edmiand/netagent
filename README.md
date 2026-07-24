# 5G Core Agent

An agentic AI assistant for managing a live **Open5GS 5G core network**.
Built with Chainlit, LangGraph, and MCP — the agent autonomously calls network
operations tools, diagnoses faults, and streams every step visibly in the UI.

---

## Architecture

```
┌─────────────────────────────┐        ┌──────────────────────────────────┐
│  VM2  (this machine)        │        │  VM1  (your 5G core host)        │
│                             │        │                                  │
│  Chainlit UI  :8000         │        │  Open5GS 5G core (systemd)       │
│  LangGraph ReAct agent      │◄─HTTP──│  MCP server (streamable HTTP)    │
│  Ollama LLM   :11434        │        │  :8080/mcp · MongoDB :27017      │
└─────────────────────────────┘        └──────────────────────────────────┘
```

**VM2 stack:** Python 3.12+ · Chainlit 2.x · LangGraph · langchain-mcp-adapters · Ollama  
**VM1 stack:** Open5GS · MCP streamable HTTP server exposing network operations tools

---

## MCP Tools (live on VM1)

| Tool | What it does |
|------|-------------|
| `system_health_snapshot` | One-shot health check of all NFs, MongoDB, and TUN device |
| `nf_lifecycle` | Start / stop / restart / status any Open5GS NF |
| `nf_resource_usage` | CPU / memory usage per NF process |
| `tail_nf_logs` | Read and filter log entries from any NF log file |
| `read_nf_config` | Read parsed YAML config for any NF (explorable subtree path) |
| `list_ue_sessions` | List all active UE registrations and PDU sessions |
| `get_ue_trace` | Call-flow trace for a UE session (rendered as Mermaid sequence diagram) |
| `amf_ran_query` | Query AMF for connected RAN / gNB info |
| `subscriber` | CRUD on subscriber profiles in MongoDB (supports filter param) |
| `subscriber_update_profile` | Update a subscriber's profile fields |
| `subscriber_update_slices` | Update a subscriber's network slice assignments |

---

## Local Tools (in-app, not MCP)

| Tool | What it does |
|------|-------------|
| `search_knowledge_base` | Semantic search over a local Chroma vector store seeded with official Open5GS documentation — grounds RCA answers in real doc content instead of relying on model memory |

Unlike the MCP tools above, this one runs entirely in-process (`agent/tools/rag.py`) — no VM1 round-trip. It's merged into the same tool list the agent sees, so the model calls it exactly like any MCP tool; it just shows up with a 📚 icon in the transcript.

**Knowledge base sources:** the 5 files under `knowledge_base/*.md` are written from real Open5GS documentation (each file cites its source URL at the top), not model-generated content — see:
- `open5gs-nf-overview.md` — https://open5gs.org/open5gs/docs/guide/01-quickstart/
- `attach-failure-modes.md` — https://open5gs.org/open5gs/docs/troubleshoot/01-simple-issues/
- `subscriber-profile-fields.md` — https://open5gs.org/open5gs/docs/tutorial/01-your-first-lte/ and .../tutorial/07-infoAPI-UE-gNB-session-data/
- `snssai-and-slicing.md` — same infoAPI/quickstart pages, plus flagged supplementary 3GPP background
- `open5gs-logs-and-configs.md` — https://open5gs.org/open5gs/docs/troubleshoot/01-simple-issues/

**Building the index:** `./webui-ctl.sh start`/`restart` auto-builds it if `data/chroma/` is missing (e.g. first run on a fresh VM, since it's gitignored). After editing any file under `knowledge_base/`, rerun it manually to pick up the changes — a stale index isn't detected automatically:
```bash
.venv/bin/python scripts/build_knowledge_base.py
```
This chunks the docs, embeds them via a local `nomic-embed-text` Ollama model, and persists vectors to `data/chroma/` (gitignored, regenerated locally — not committed).

---

## Prerequisites

### VM1 — must already be running
- Open5GS 5G core installed and started
- MCP streamable HTTP server running on port 8080 (`http://<VM1-IP>:8080/mcp`)

### VM2 — this machine
- Ubuntu 22.04 or 24.04 (other Debian-based distros should work)
- Python 3.12+ (see [System dependencies](#1-system-dependencies) below)
- [Ollama](https://ollama.com) installed and running at `http://localhost:11434` (API gateway only for chat models — no GPU required; the RAG knowledge-base tool does need one small local model pulled, see step 3 below)
- Network access to VM1 on port 8080
- Port 8000 open for inbound connections (Chainlit UI)
- Outbound internet access to `https://mermaid.ink` (call flow diagram rendering — no install needed, falls back to raw Mermaid code if unreachable)

---

## Fresh VM Setup

Follow these steps in order on a clean Ubuntu VM. Each section is a
self-contained block of shell commands you can copy and run as-is.

### 1. System dependencies

```bash
sudo apt-get update
sudo apt-get install -y git curl build-essential

# Ubuntu 24.04 ships Python 3.12 — already satisfies >=3.12, skip the next block.
# Ubuntu 22.04 ships Python 3.10 — add deadsnakes PPA to get 3.12:
sudo apt-get install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
```

> **Ubuntu 24.04 users:** replace `python3.12` with `python3` in all commands
> below — the system Python is already 3.12.

### 2. Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh

# The installer registers and starts the ollama systemd service automatically.
# Verify it is running:
systemctl status ollama
```

### 3. Configure cloud models

This app uses **cloud-hosted models** (`gemma4:31b-cloud`, `gpt-oss:20b-cloud`)
— no local GPU is required. Ollama serves as the API gateway only; the model
computation runs in the cloud.

No `ollama pull` is needed for chat. Verify Ollama is reachable and leave the
default `active` entry in `config/models.yaml` as-is:

```yaml
active: gemma4:31b-cloud
```

> **Do not** pull `qwen2.5:7b` or other local chat models — they require a
> GPU and will be slow or fail on a CPU-only VM.

**Exception — embeddings model (small, CPU-friendly):** the RAG knowledge-base
tool (`search_knowledge_base`) needs a local embeddings model, since Ollama
Cloud doesn't serve embeddings the same way it serves chat completions:

```bash
ollama pull nomic-embed-text   # ~274MB, runs fine on CPU
```

This is configured in `config/models.yaml` under the `embeddings:` block —
see [Configuration](#configuration) below.

### 4. Open the firewall (if UFW is active)

```bash
# Allow inbound traffic to the Chainlit UI
sudo ufw allow 8000/tcp
sudo ufw status
```

### 5. Clone and install the app

```bash
# Clone
git clone git@github.com:edmiand/netagent.git
cd netagent

# Create and activate virtualenv (adjust python3.12 → python3 on Ubuntu 24.04)
python3.12 -m venv .venv
source .venv/bin/activate

# Install all Python dependencies
pip install --upgrade pip
pip install -e .

# Copy environment file and generate a JWT secret (required by Chainlit auth)
cp .env.example .env
echo "CHAINLIT_AUTH_SECRET=$(openssl rand -hex 32)" >> .env
```

### 6. Point the app at your VM1

Edit `config/mcp.yaml` and set the correct IP/port for your VM1:

```yaml
servers:
  open5gs:
    transport: streamable_http
    url: http://<VM1-IP>:8080/mcp   # ← replace with your VM1 address
```

### 7. Set the active model

Edit `config/models.yaml` and set `active` to your preferred cloud model:

```yaml
active: gemma4:31b-cloud   # or gpt-oss:20b-cloud
```

### 8. RAG knowledge base

No manual step needed — `./webui-ctl.sh start` (step 11) auto-builds
`data/chroma/` the first time it's missing. To build it explicitly instead
(e.g. to check it works before starting the app):

```bash
.venv/bin/python scripts/build_knowledge_base.py
# Chunks knowledge_base/*.md, embeds via nomic-embed-text, persists to data/chroma/
```

### 9. Run the integration tests (optional but recommended)

```bash
source .venv/bin/activate
python test_integration.py
# Exit code 0 = LLM reachable · MCP tools loaded · agent round-trip OK
```

### 10. Enable the app to start on boot (recommended)

```bash
./scripts/install_service.sh
```

This creates and enables a `systemd --user` service (`netagent-app.service`)
and turns on lingering (`loginctl enable-linger`) so the app comes back up
automatically after a reboot — no login session required. `webui-ctl.sh`
auto-detects this service once installed and delegates `start`/`stop`/
`restart`/`status` to `systemctl --user` instead of managing a raw `nohup`
process. Safe to skip if you'd rather start the app manually each time.

### 11. Start the app

```bash
./webui-ctl.sh start          # start in background, logs → chainlit.log
./webui-ctl.sh status         # check it's running
./webui-ctl.sh logs           # tail -f the log
./webui-ctl.sh stop           # graceful stop + port release
./webui-ctl.sh restart        # stop then start
```

Open **http://\<VM2-IP\>:8000** in a browser.

---

## Quick start (existing VM)

If the VM already has Python 3.12+, Ollama running, and VM1 reachable:

```bash
git clone git@github.com:edmiand/netagent.git
cd netagent
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env
echo "CHAINLIT_AUTH_SECRET=$(openssl rand -hex 32)" >> .env
# Edit config/mcp.yaml → set VM1 address
ollama pull nomic-embed-text          # embeddings model for the RAG tool
./scripts/install_service.sh          # optional: auto-start on boot
./webui-ctl.sh start                  # auto-builds the RAG knowledge base on first run
```

---

## Configuration

### Model — `config/models.yaml`

```yaml
active: gemma4:31b-cloud   # ← change this line to switch models
```

Available cloud entries: `gemma4:31b-cloud`, `gpt-oss:20b-cloud`.  
No GPU required — Ollama is used as a gateway only.  
Restart Chainlit after changing.

### Embeddings — `config/models.yaml`

```yaml
embeddings:
  model: nomic-embed-text
  base_url: http://localhost:11434
```

Used only by `search_knowledge_base` (`agent/tools/rag.py`) and the build
script. Unlike chat models, this runs **locally** — requires
`ollama pull nomic-embed-text` once (see Prerequisites above).

### MCP server — `config/mcp.yaml`

```yaml
servers:
  open5gs:
    transport: streamable_http
    url: http://<VM1-IP>:8080/mcp  # ← replace with your VM1 address
```

---

## Project layout

```
app.py                  # Chainlit entry point — chat lifecycle + streaming
start.py               # Wrapper: syncs branding.yaml → config.toml, then launches Chainlit
webui-ctl.sh           # Process manager: start / stop / restart / status / logs
agent/
  llm.py               # LangChain model loader (reads config/models.yaml) + get_embeddings()
  mcp_bridge.py        # SSE client via MultiServerMCPClient
  graph.py             # LangGraph ReAct agent (create_react_agent)
  approval.py          # wrap_with_approval() — generic, works on any tool (MCP or local)
  tools/
    rag.py              # search_knowledge_base — local RAG tool over the Chroma store
config/
  models.yaml          # Model registry, active model selection, embeddings config
  mcp.yaml             # MCP server URL (update VM1 IP here)
  branding.yaml        # Agent name, welcome title, logo file
prompts/
  system.txt           # Agent system prompt — behaviour rules and formatting
knowledge_base/
  *.md                 # Open5GS-doc-sourced reference notes (each cites its source URL)
scripts/
  build_knowledge_base.py  # Chunk + embed knowledge_base/*.md → data/chroma/ (auto-run by webui-ctl.sh start if missing; rerun manually after editing knowledge_base/*.md)
data/
  chroma/               # Persisted RAG vector store (gitignored, generated by the build script)
.env.example           # Environment template (copy to .env — OLLAMA_API_KEY=ollama)
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
- `what does "Authentication failure(MAC failure)" mean?` — triggers `search_knowledge_base`

### Call flow diagrams

Ask the agent about any 5G procedure and it will produce a Mermaid sequence diagram rendered as an inline PNG:

- `show me the 5G registration call flow`
- `draw the PDU session establishment procedure`
- `what does the authentication flow look like between UE, AMF, and AUSF?`

**How it works:** the agent generates Mermaid syntax → `app.py` base64-encodes it and fetches a PNG from `https://mermaid.ink` → the image embeds inline in the chat.  
**Dependencies:** none beyond `pip install -e .` (`httpx` is already included). Requires outbound internet access to `mermaid.ink`. If the fetch fails, the raw Mermaid code block is shown as a fallback.

---

## Switching models

```bash
# Edit config/models.yaml — choose from the cloud-hosted entries
active: gpt-oss:20b-cloud   # or gemma4:31b-cloud

# No ollama pull needed — these models run in the cloud

# Restart the app
./webui-ctl.sh restart
```

---

## Updating the Knowledge Base

The `search_knowledge_base` tool is backed by a local vector index built
from `knowledge_base/*.md`. Editing those files does **not** update the
tool's answers by itself — the index is a separate, generated artifact
(`data/chroma/`) that has to be rebuilt explicitly.

**To add or edit a doc:**

1. Add a new `.md` file under `knowledge_base/`, or edit an existing one.
   Cite the source (an official Open5GS doc URL, or clearly flag it as
   supplementary background) at the top of the file — see the existing
   files for the pattern.
2. Rebuild the index:
   ```bash
   .venv/bin/python scripts/build_knowledge_base.py
   ```
   This re-chunks and re-embeds **all** files under `knowledge_base/`, not
   just the one you changed, and overwrites `data/chroma/`.
3. Restart the app so the running agent picks up the new tool state:
   ```bash
   ./webui-ctl.sh restart
   ```

**Note:** `./webui-ctl.sh start`/`restart` only auto-builds the index if
`data/chroma/` is **missing entirely** (e.g. a fresh VM) — it does not
detect that the index is stale relative to the `.md` source files. Step 2
above must be run manually any time `knowledge_base/*.md` changes.

To verify the update took effect, ask the agent something that should
retrieve the new/changed content and confirm a `📚 search_knowledge_base`
step appears with the expected text.

---

## Running tests

```bash
source .venv/bin/activate
python test_integration.py
```

Tests check: LLM reachability · MCP tool loading (required tools present) · agent round-trip invocation.  
Exit code 0 = all pass.

---

## Known constraints

- **Chainlit 2.x API** — do not use v1 patterns (`@cl.langchain_factory`, etc.)
- **`.chainlit/config.toml`** — delete and let Chainlit regenerate if you see *"config file is outdated"*
- **UPF operations** on VM1 may require `sudo` — the MCP server handles privilege escalation
- **Ollama API key** is set to the literal string `ollama` — this is correct, Ollama does not validate it
