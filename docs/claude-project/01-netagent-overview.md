# NetAgent — project overview

> Project knowledge file 1 of 7 · snapshot of the `netagent` repo as of 2026-11-04 (commit 9d501a7).
> Start here. Paths like `agent/graph.py` refer to the code repo, which is not attached to this
> Project — ask for a file's contents if a question depends on exact code.

## What it is

NetAgent is an agentic AI assistant for operating a live **Open5GS 5G core network**. An operator
chats with it in a web UI. A LangGraph ReAct agent chains tool calls to inspect the core,
diagnose faults (root-cause analysis, RCA) and take remediation actions. Every tool call streams
into the UI as a visible, expandable step.

It is a demo/showcase system: one lab 5G core, simulated UEs (UERANSIM), cloud-hosted LLMs.

## Architecture

```
┌──────────────────────────────┐            ┌─────────────────────────────────┐
│ VM2 — NetAgent               │            │ VM1 — 5G core                   │
│ Chainlit web UI   :8000      │  HTTP      │ Open5GS NFs (native processes)  │
│ LangGraph ReAct agent        │──────────▶ │ MCP server (streamable HTTP)    │
│ Ollama gateway    :11434     │            │   :8080/mcp                     │
│ Local tools (RAG, Hedera, …) │            │ MongoDB :27017 (subscribers)    │
└──────────────────────────────┘            └─────────────────────────────────┘
```

- **VM1** runs Open5GS (AMF, SMF, UPF, NRF, UDM, UDR, AUSF, PCF, BSF, NSSF) as native Linux
  processes — not Kubernetes — plus an MCP server exposing network operations as tools.
  NetAgent never modifies VM1 itself; it only calls its MCP tools.
- **VM2** runs the Chainlit app, the agent and Ollama. The MCP connection is just a URL
  (`config/mcp.yaml`); there is no local MCP process.
- **LLMs:** Ollama acts as a gateway to cloud-hosted models (no GPU needed). One models.yaml entry
  (`local-ollama`) points at a model running on the operator's Apple Silicon host Mac, for
  on-prem inference where no prompt leaves the site.
- **UEs:** UERANSIM simulates UEs and a gNB; each attached UE gets a tunnel interface
  (`uesimtun0`, …).

## Stack

Python 3.11+ · Chainlit 2.x · LangGraph 1.2.x (`create_react_agent`) · langchain-mcp-adapters 0.3.x
· langchain-ollama · Chroma + `nomic-embed-text` embeddings (local Ollama) · SQLite chat history
(SQLAlchemy + aiosqlite) · Tavily (release lookups) · hiero-sdk-python (Hedera, Pre-Alpha, pinned)
· eqty_sdk + eqty-lineage-langchain (lineage manifests). Dependencies are pinned in `pyproject.toml`.

## Tools the agent can call

The agent learns tool schemas from the tools themselves; the system prompt never lists tools.

### MCP tools (on VM1)

| Tool | Purpose |
|---|---|
| `system_health_snapshot` | One-shot health of all NFs, MongoDB and the TUN device |
| `nf_lifecycle` | Start / stop / restart / status of any NF |
| `nf_resource_usage` | CPU / memory per NF process |
| `tail_nf_logs` | Filtered reads of NF log files |
| `read_nf_config` | Parsed YAML config of an NF; optional dotted path (`amf.sbi.server.0`); a bad path returns the sibling keys, so it is explorable |
| `list_ue_sessions` | Active UE registrations and PDU sessions |
| `get_ue_trace` | Call-flow trace for a UE session (rendered as a Mermaid sequence diagram) |
| `amf_ran_query` | Connected RAN / gNB info from the AMF |
| `subscriber` | CRUD on subscriber profiles in MongoDB (supports a `filter`); a destructive change can first return a preview with `confirm_required: true` |
| `subscriber_update_profile` | Update a subscriber's profile fields |
| `subscriber_update_slices` | Update a subscriber's network-slice (S-NSSAI) assignments |
| `open5gs_version` | Compiled Open5GS version: `{tag, commits_since_tag, commit_hash, raw}` |
| `send_ue_notification` | Push a short text to a UE over its own PDU session: VM1 resolves IMSI → UE IP via the SMF and POSTs `{message, incident_id}` to `http://<ue_ip>:9000/notify` |

MCP tools return structured data (dicts/JSON), never raw strings.

### Local tools (in-process on VM2)

| Tool | Purpose |
|---|---|
| `search_knowledge_base` | Semantic search (Chroma) over `knowledge_base/*.md` — Open5GS documentation notes plus NetAgent's UE-notification policy (file 7). Returns prose, deliberately, as grounding text |
| `check_open5gs_release_info` | Tavily lookup pinned to github.com/open5gs/open5gs: "what changed upstream since version X". Takes only a `version` argument; the model can't compose a free-text query. Pairs with `open5gs_version` |
| `hcs_submit_message`, `hcs_read_message`, `hcs_list_recent`, `hcs_verify_report` | Hedera Consensus Service audit trail (file 3). Only offered when `config/hedera.yaml` has `enabled: true` |
| `recall_similar_incidents`, `record_incident` | Memory & Learning: a Chroma store of past resolved incidents (NF, symptom, root cause, fix). Only offered when the ⚙️ "Memory & Learning" toggle is on |

### Specialist sub-agents

The main agent acts as a supervisor and can delegate to two specialists. Each is its own bounded
`create_react_agent` over a narrow, read-only tool subset with its own prompt, and returns a
synthesized report. Remediation (subscriber writes, NF lifecycle) stays with the supervisor and
the user.

| Specialist (tool name) | Tools it can use |
|---|---|
| Connectivity Investigator (`investigate_connectivity`) | `list_ue_sessions`, `get_ue_trace`, `amf_ran_query`, `subscriber`, `tail_nf_logs` |
| NF Health Investigator (`investigate_nf_health`) | `system_health_snapshot`, `tail_nf_logs`, `nf_resource_usage`, `read_nf_config` |

## Web UI features

**Buttons on every message:**
- 🏥 **Health Snapshot** — `system_health_snapshot`, NF status table with 🟢🟡🔴.
- 👀 **Watch Subscriber Attach** — `list_ue_sessions`, registered UEs and PDU sessions.
- 🔍 **Debug Attach Failure** — the full RCA chain (health → logs → config → sessions →
  subscriber checks), reported as **Root cause / Evidence / Recommended action**.
- 📜 **Audit Trail** (Hedera enabled) — latest 10 ledger entries with a HashScan link.
- 🧬 **Lineage** (lineage viewer enabled) — links to this chat's EQTY lineage graph and manifest
  download (file 5). Plain code, no agent call.
- 🔏 **Fingerprint report** — only under RCA replies (detected by the `**Root cause:**` heading):
  hashes the displayed report in code and records the SHA-256 on Hedera.

**⚙️ Settings (per chat):**
- **Model** — picks the model for this chat only (shown when more than one model is enabled).
  Rebuilds the agent and the specialists; nothing is written back to config.
- **Human Approval Mode** — every tool call (MCP or local, including mid-RCA) shows an
  approve/deny prompt; unanswered prompts auto-deny after 120 s.
- **Use Model Reasoning** / **Show Model Thinking** — only for models with `thinking: true`.
  The second streams reasoning tokens into a "💭 Reasoning" step.
- **Memory & Learning** — adds the incident-memory tools.

**Other behaviour:**
- A collapsed **📊 Context** step after each reply shows that turn's token usage.
- Call flows render as **Mermaid sequence diagrams** via the mermaid.ink API (PNG sent as a
  separate message; the raw Mermaid code is the fallback).
- **Chat history** persists in SQLite. A chat reopened from history is read-only (start a new chat
  to keep working); threads auto-name from the first message.
- Authentication is a header-auth stub: every visitor is the same `demo` user.

## Agent behaviour rules (system prompt)

- Call tools immediately; no preamble ("let's call X…"). Never suggest shell commands, kubectl or
  systemctl. Never mention a tool that isn't in the current tool list.
- **Lifecycle operations** (start/stop/restart a NF): exactly one tool call per response, then stop
  and report. Never touch a NF's lifecycle unless the user explicitly asks.
- `confirm_required: true` in a tool result is treated like a destructive operation: show the
  preview, wait for the user's explicit yes, then re-call with `confirm=true`.
- **UE notifications**: one call per UE, only after an incident-related change is applied and
  verified (policy in the knowledge base).
- **Audit trail** (when the hcs tools exist): one short entry after each successful change, one
  summary per batch, one per confident RCA, and whenever asked. Never for reads, health checks,
  or denied/failed actions. Format `<action> — <target> — <outcome>`; no IMSIs, IPs or keys.
- **Read-only/bulk requests** and the **RCA workflow** may chain many tool calls in one turn —
  intentional, not a violation of the one-call rule.
- Don't proactively check NF health in normal conversation — only on request or during RCA.
- No LaTeX (the app still rewrites stray `$\longrightarrow$` to Unicode after streaming).

## Configuration files

| File | Holds |
|---|---|
| `config/models.yaml` | Model registry; `active` = default for new chats; per entry `base_url`, `temperature`, `max_tokens`, `context_window` (→ Ollama `num_ctx`), `thinking`, optional `model:` (real Ollama name when it differs from the picker label), `enabled: false` to hide; plus the `embeddings:` block |
| `config/mcp.yaml` | MCP server URL on VM1 (gitignored, per deployment) |
| `config/hedera.yaml` | Audit trail: `enabled`, network, mirror URL, explorer URL, fixed `topic_id` |
| `config/lineage.yaml` | `viewer_enabled` for the 🧬 Lineage viewer |
| `config/branding.yaml` | Agent name, welcome title, logo — synced into Chainlit's config at start |
| `prompts/system.txt` | Main system prompt; `prompts/subagents/*.txt` for specialists |
| `.env` | Secrets: `CHAINLIT_AUTH_SECRET`, `TAVILY_API_KEY`, `HEDERA_OPERATOR_ID` / `HEDERA_OPERATOR_KEY` (DER), optional `EQTY_NOTARY_URL` |

Current models: `gemma4:31b-cloud` (default), `gpt-oss:120b-cloud`, `nemotron-3-ultra:cloud`,
`local-ollama` (host Mac), and `qwen2.5:7b` (disabled). All enabled ones have `thinking: true`.

## Code layout

```
app.py              Chainlit entry point: chat lifecycle, streaming, buttons, settings, LaTeX/Mermaid rewrites
start.py            Syncs branding into .chainlit/config.toml, then launches Chainlit
netagent.sh         start | stop | restart | status | logs (delegates to a systemd --user unit if installed)
data_layer.py       SQLite chat history + local file storage for elements
lineage_viewer.py   /lineage/<chat_id> routes + lineage_viewer.html page
agent/
  llm.py            Model loader from models.yaml; get_embeddings()
  mcp_bridge.py     MultiServerMCPClient over streamable HTTP
  graph.py          The LangGraph ReAct agent
  subagents.py      The two specialists
  approval.py       Human Approval wrapper around every tool
  tools/            rag.py · release_check.py · hedera.py · memory.py
prompts/            system.txt · subagents/
knowledge_base/     RAG source docs (file 7)
scripts/            build_knowledge_base.py · rca_bench.py · ue_notify_listener.py · seed_memory_store.py · install_service.sh
test_integration.py LLM reachable · MCP tools load · agent round trip · optional Hedera round trip
```

## Constraints and known gotchas

- **Do not modify anything on VM1.** No hardcoded IPs, URLs or model names — always from config.
- Chainlit 2.x only (no v1 patterns). Don't hand-write `.chainlit/config.toml`; delete it and let
  Chainlit regenerate it.
- Chainlit 2.x: starters only render on an empty chat (hence buttons on every message); elements
  added to a streamed message via `update()` are silently dropped — send a new message instead.
- langgraph 1.2.x: `create_react_agent(prompt=…)`, not `state_modifier=`. langchain-mcp-adapters
  0.3.x: `MultiServerMCPClient` is not an async context manager — call `await client.get_tools()`.
- Mermaid is rendered remotely (mermaid.ink) because the headless-Chrome renderer is x86-only and
  VM2 is ARM.
- The knowledge-base index (`data/chroma/`) is generated and gitignored; it must be rebuilt after
  editing `knowledge_base/*.md`, then the app restarted (the Chroma handle is cached).
- UPF operations on VM1 may need sudo — the MCP server handles it.
- Human Approval Mode necessarily interrupts the RCA's "no text between tool calls" flow; expected.
