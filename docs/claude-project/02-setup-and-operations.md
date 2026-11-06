# NetAgent — setup and operations

> Project knowledge file 2 of 7 · snapshot as of 2026-11-04 (commit 9d501a7).
> How to deploy, run, configure and test NetAgent on VM2. Architecture and features are in file 1.

## Prerequisites

- **VM1:** Open5GS running, MCP server at `http://<VM1-IP>:8080/mcp`.
- **VM2:** Ubuntu 22.04/24.04, Python 3.11+, Ollama at `http://localhost:11434`, network access to
  VM1:8080, inbound port 8000 (UI), outbound access to `mermaid.ink` (diagrams; falls back to raw
  Mermaid) and `cdn.jsdelivr.net` (lineage viewer, from the browser).

## Fresh VM setup

1. **System packages:** `git curl build-essential`; on 22.04 add Python 3.11 from the deadsnakes PPA
   (24.04's Python 3.12 already qualifies).
2. **Ollama:** `curl -fsSL https://ollama.com/install.sh | sh` (installs and starts the service).
3. **Models:** chat models are Ollama Cloud — no `ollama pull` needed for chat. Don't pull local chat
   models on a CPU-only VM. **Exception:** `ollama pull nomic-embed-text` (~274 MB, CPU-fine) for
   the knowledge-base and memory tools.
4. **Firewall:** `sudo ufw allow 8000/tcp` if UFW is active.
5. **Install:**
   ```bash
   git clone <repo> && cd netagent
   python3 -m venv .venv && source .venv/bin/activate
   pip install --upgrade pip && pip install -e .
   cp .env.example .env
   echo "CHAINLIT_AUTH_SECRET=$(openssl rand -hex 32)" >> .env
   ```
   Always use `.venv/bin/python` / `.venv/bin/pip`. `pyproject.toml` is the only source of
   pinned versions.
6. **Point at VM1:** set the URL in `config/mcp.yaml`:
   ```yaml
   servers:
     open5gs:
       transport: streamable_http
       url: http://<VM1-IP>:8080/mcp
   ```
7. **Default model:** `active:` in `config/models.yaml` (users can switch per chat in ⚙️ Settings).
8. **Knowledge base:** auto-built on first start if `data/chroma/` is missing.
9. **Test:** `.venv/bin/python test_integration.py` — exit 0 = LLM reachable · MCP tools loaded ·
   agent round trip OK (a 4th Hedera round-trip check runs only when Hedera is enabled).
10. **Auto-start on boot (optional):** `./scripts/install_service.sh` installs a systemd `--user`
    unit (`netagent-app.service`) and enables lingering. `netagent.sh` then delegates to systemctl.
11. **Run:** `./netagent.sh start | stop | restart | status | logs`, then open `http://<VM2-IP>:8000`.

Optional secrets in `.env`: `OPENAI_API_KEY` (shows the `openai-*` models; switch them all off
with `providers.openai.enabled: false` in `config/models.yaml`), `TAVILY_API_KEY` (release lookups degrade gracefully without it),
`HEDERA_OPERATOR_ID` / `HEDERA_OPERATOR_KEY` (DER-encoded; see file 3), `EQTY_NOTARY_URL` (file 5).
After the first run on a fresh install: `chmod 700 .eqty_sdk` (holds the lineage signing key).

## Changing things

| Change | Steps |
|---|---|
| Default model / model list | Edit `config/models.yaml` (`active:`; keys are `ollama-<tag>` / `openai-<model>`), `./netagent.sh restart`. Default is `openai-gpt-6-luna`, falling back to `ollama-gemma4:31b-cloud` without an OpenAI key |
| Add a model | New `models:` entry; `context_window` from the model's ollama.com page; `thinking: true` only if it supports it; it must support tool calling |
| Local model on the host Mac | Pull it there, add or edit an `ollama-<tag>` entry (`model:` = the Ollama tag; `base_url: *mac_ollama`), restart. The Mac's Ollama must listen beyond localhost (`OLLAMA_HOST=0.0.0.0`) |
| Knowledge-base docs | Edit/add `knowledge_base/*.md` (cite the source URL at the top), run `.venv/bin/python scripts/build_knowledge_base.py`, restart. Start only auto-builds a *missing* index, never a stale one |
| Hedera on/off, topic | `config/hedera.yaml`, restart (the write client caches the topic) |
| Lineage viewer on/off | `config/lineage.yaml` `viewer_enabled`, restart |
| Branding | `config/branding.yaml` (`agent_name`, `welcome_title`, `logo_file` in `public/logos/`), restart |
| "config file is outdated" from Chainlit | Delete `.chainlit/config.toml`, restart |

## UE notification listener

`send_ue_notification` needs a receiver on the UE side: `scripts/ue_notify_listener.py`
(stdlib only), run on the UERANSIM host.

```bash
.venv/bin/python scripts/ue_notify_listener.py                      # uesimtun0, port 9000
.venv/bin/python scripts/ue_notify_listener.py -i uesimtun1 -p 9000  # a second UE
```

- Waits for the interface and its IPv4, binds that address only (never 0.0.0.0), so it is
  reachable only through the PDU session.
- `POST /notify` with `{"message": "...", "incident_id": "..."}` → prints a timestamped line,
  returns 200 + JSON ack; anything else → 4xx.
- One instance per UE interface. Restart it if the UE re-attaches with a new IP.

Try: `notify imsi-<IMSI> that the SMF was restarted and data service is restored, incident INC-TEST-1`

## Vetting a model: `scripts/rca_bench.py`

Runs the "Debug Attach Failure" RCA headlessly against one models.yaml entry and reports the tool
sequence, timing and whether the reply has the required Root-cause heading. Never writes to the
Hedera topic (omits the hcs tools). `--no-reasoning` compares with reasoning off. Use it before
making a new or local model the default.

## Example prompts

```
show subscriber imsi-999700000000001
tail amf logs for the last 10 minutes
restart the nssf
what is the AMF SBI address?
create 5 subscribers starting from imsi-999700000000010
what does "Authentication failure(MAC failure)" mean?     → search_knowledge_base
what version of open5gs are we on, and what changed since? → open5gs_version + release check
show me the 5G registration call flow                      → Mermaid diagram
```

## Troubleshooting quick list

| Symptom | Likely cause |
|---|---|
| Chat start fails with `ConnectError` | VM1's MCP server unreachable |
| Buttons do nothing | Chat reopened from history (read-only) — start a new chat |
| Knowledge-base answers outdated | Index stale — rebuild and restart |
| Knowledge-base tool errors after a rebuild | App not restarted (cached handle to the deleted collection) |
| No 💭 Reasoning toggles | Selected model has no `thinking: true` |
| Raw LaTeX flickers then turns into arrows | Expected: rewritten to Unicode when streaming completes |
