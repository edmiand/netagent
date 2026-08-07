# Roadmap

## Split `prompts/system.txt` via classification + prompt-swap

**Problem:** `prompts/system.txt` (~78 lines) covers identity/hard rules, intent
routing, domain knowledge, formatting, the full RCA workflow, and communication
rules all at once, sent to the model on every turn. This is a lot for a local
Ollama model to hold reliably, and it grows every time a new behaviour is added.

**Approach (chosen over a full LangGraph multi-agent/supervisor rewrite — see
"Alternatives considered" below):** keep the single `create_react_agent` in
`agent/graph.py`, but classify each incoming message and assemble only the
relevant prompt modules for that turn, instead of always sending the whole file.

### 1. Split `prompts/system.txt` into a shared core + topic modules
- `prompts/core.txt` — identity + always-on hard rules (never suggest shell
  commands, never invent tools, destructive-op = one tool call, chaining rule).
  Always included.
- `prompts/routing.txt` — intent-routing table (which tool for which phrasing).
- `prompts/domain.txt` — subscriber/slice/status/AMBR domain knowledge.
- `prompts/formatting.txt` — status emoji legend + health snapshot table format.
- `prompts/rca.txt` — RCA 6-step sequence + subscriber attach triage heuristics.
- `prompts/communication.txt` — plain-English/Mermaid diagram rules.

### 2. Add a classifier to pick modules per turn
New `agent/prompt_router.py` with `classify(user_input: str) -> set[str]`.
Rule-based/keyword, not LLM-based (this is a demo app with known entry points):
- Health Snapshot button → `formatting`
- Watch Subscriber Attach button → `formatting`
- Debug Attach Failure button → `rca` + `domain` + `formatting`
- Free-text messages → keyword match (e.g. "attach failure"/"debug"/"root
  cause" → `rca`; "subscriber"/"slice"/"DNN" → `domain`); default fallback
  includes `routing` + `formatting`.
- The three demo buttons in `app.py` (`_make_scenario_actions`) should tag
  their payload with an explicit category so their classification is exact,
  not inferred from keyword matching.

### 3. Assemble the prompt per turn, not once at session start
`agent/graph.py::create_agent` currently reads `system.txt` once at
`on_chat_start` and bakes it into the graph. Change to build `core + selected
modules` per invocation — either via LangGraph's `prompt=` accepting a
callable that inspects the latest `HumanMessage`, or by passing the selected
modules through the invocation `config`'s `configurable` dict for the
prompt-builder to read. Prefer the callable-prompt approach — avoids
rebuilding the graph/checkpointer per message.

### 4. Wire into `app.py`
`_run_agent()` (app.py:318) calls `agent.astream_events(...)` with raw
`user_input`. Classification needs to happen right before this call and its
result needs to reach the prompt-builder via whichever mechanism from step 3
is chosen.

### Known trade-offs / open questions
- `MemorySaver` checkpoints conversation history per `thread_id`; swapping the
  system prompt mid-thread means later turns may see different rules than
  earlier turns did. Fine for this demo's single-shot interactions, worth
  revisiting if multi-turn RCA follow-ups are added later.
- Keyword classification is the weak point. Need to decide whether
  misclassification should fail toward *including more modules* (safer, less
  prompt savings) or *fewer* (more savings, more risk of dropping rules like
  "no text between tool calls" from an actual RCA request).
- This only reduces system-prompt text, not MCP tool schema size — if tool
  schema bulk is part of the bloat, this doesn't address it.

### Alternatives considered
- **Prompt-only split, no classifier:** just break the file into sections and
  always concatenate them — no bloat reduction, only readability. Rejected as
  not actually solving the size problem.
- **True LangGraph subagents (supervisor pattern):** replace the single
  ReAct agent with a supervisor routing to specialized agents (RCA agent,
  subscriber-mgmt agent, query/reporting agent), each with its own short
  prompt and tool subset. This is the "real" fix and gives independent
  agents, but is a much bigger architecture change (new graph topology,
  routing logic, per-subagent tool wiring, retesting the "one tool call for
  lifecycle ops" and "no preamble" rules per node). Deferred — revisit if the
  classification approach turns out insufficient.

---

## Additional tools/resources to strengthen the Agentic AI demo

**Context:** current demo has one MCP server (VM1/Open5GS) and three scenario
buttons (health snapshot, watch attach, debug attach failure/RCA). No metrics
store, vector DB, ticketing, or alerting integration exists yet. The additions
below each showcase a distinct agentic capability rather than just adding more
tools for their own sake.

Priority order (highest demo payoff for effort first):

### 1. Vector store for RCA grounding (RAG) — ✅ DONE
- Implemented: local Chroma store (`data/chroma/`), embeddings via
  `nomic-embed-text` on the existing local Ollama instance
  (`agent/llm.py::get_embeddings()`), 5 seed docs under `knowledge_base/*.md`
  sourced from real Open5GS documentation (each file cites its source URL —
  guide/01-quickstart, troubleshoot/01-simple-issues,
  tutorial/01-your-first-lte, tutorial/07-infoAPI-UE-gNB-session-data).
- `agent/tools/rag.py::search_knowledge_base` — local (non-MCP) LangChain
  tool, merged into the same tool list as the MCP tools in
  `app.py::_build_tools()`. `prompts/system.txt` nudges the RCA flow to call
  it when a failure cause is ambiguous.
- `netagent.sh start`/`restart` auto-builds `data/chroma/` if missing (e.g.
  first run on a fresh VM) — no manual step needed for a new deploy. Editing
  `knowledge_base/*.md` still requires manually rerunning
  `scripts/build_knowledge_base.py` to refresh a stale index (not detected
  automatically).
- **Not yet done (follow-up):** persisting past RCA reports from
  `data_layer.py`'s chat history into the same store for episodic memory
  ("have we seen this failure before?") — deferred, still a good next step.

### 2. Fault injection tool
- A `fault_injection` tool wrapping something like UERANSIM (synthetic UE
  attach/detach) or a scripted, reversible config perturbation, so failures
  can be triggered on demand instead of relying on organic network state.
- Makes "Debug Attach Failure" reliable to demo live instead of hoping
  something is actually broken at demo time.
- Needs care re: "Do not modify anything on VM1" constraint — likely needs
  to be an additive/reversible tool rather than a direct config edit, or
  requires explicit sign-off to relax that constraint for a sandboxed fault
  path.

### 3. Notification / ticketing action tools
- Notification tool (Slack webhook or email) the agent calls after RCA to
  "page oncall" — demonstrates closing the loop from diagnosis to action.
  Pairs naturally with the existing Human Approval Mode toggle as a gate
  before it fires.
- Ticketing tool (Linear/Jira, or a local SQLite `incidents` table if
  avoiding external deps) where the agent files a structured incident report
  after RCA — shows multi-step tool orchestration producing a durable
  artifact, not just chat text.

### 4. Time-series metrics for trend reasoning
- Prometheus + lightweight exporter on VM1, or simpler: scrape
  `nf_resource_usage` on an interval into a local SQLite/TimescaleDB.
- Lets the agent reason over trends instead of point-in-time snapshots
  (e.g. "UPF memory has climbed 40% over the last hour") — stronger
  autonomous-diagnosis demo than a single snapshot check.
- Grafana as a companion dashboard is optional polish, not required for the
  agent itself.

### 5. Multi-agent orchestration (supervisor pattern)
- Same as the "Alternatives considered" supervisor-pattern option above —
  listed here too because it's arguably the single highest-leverage
  "agentic AI" demo item: visibly showcases autonomy/delegation across
  specialized subagents in a way a single ReAct loop can't.
- Biggest lift of everything on this list; revisit after the cheaper items
  above are in place.

### 6. Release / advisory check tool (narrow internet lookup) — ✅ DONE
- Implemented: `agent/tools/release_check.py::check_open5gs_release_info`,
  merged into the tool list in `app.py::_build_tools()` alongside
  `search_knowledge_base`. Backed by `tavily-python`, domain pinned to
  `github.com/open5gs/open5gs` (NVD dropped for now — revisit if the
  advisory use case needs CVE coverage beyond what GitHub issues mention).
  Reads `TAVILY_API_KEY`
  from `.env` (see `.env.example`); degrades gracefully with a clear
  message when the key is unset, same pattern as the RAG tool's
  "not built yet" case.
- `prompts/system.txt` Domain Knowledge section tells the agent to call it
  only once it has a specific version string in hand (from a config value
  or log banner) — never as a general search.
- **Not yet done:** live validation against VM1's actual running Open5GS
  version and a Tavily key — needs a real API key to test end-to-end and
  rehearse before a demo.
- **Problem it solves:** both existing knowledge sources are frozen — the
  Chroma index at last `build_knowledge_base.py` run, the model at its
  training cutoff. Neither can answer "you're running 2.7.2, what has
  landed upstream since?" That staleness gap is the *only* thing this item
  is for.
- New local (non-MCP) tool, `agent/tools/release_check.py`, merged into the
  same tool list in `app.py::_build_tools()` — same pattern as
  `search_knowledge_base`. Backed by Tavily (free tier, 1000 calls/mo,
  API key in `.env`); returns structured JSON, not raw HTML.
- **Deliberately not a general web search tool.** Single purpose, single
  argument: `check_open5gs_release_info(version)`. The agent passes a
  version string and nothing else — it never composes the query. Query
  shape is hard-coded in the tool; domains pinned to the Open5GS GitHub
  releases/issues and NVD.
- Why narrowed (the general `web_search` version was considered and
  rejected):
  - **Routing overlap.** A general "search the web about Open5GS" tool
    sits directly on top of `search_knowledge_base`'s meaning. Expecting a
    local Ollama model to arbitrate that reliably is optimistic; the
    likely outcome is the agent reaching for the internet on questions the
    KB already answers, making responses slower and less grounded. A tool
    whose name states its trigger has no such ambiguity.
  - **Demo determinism.** Every other tool returns data from a machine we
    control. Open-ended search results change under us between rehearsal
    and demo; release notes don't.
  - **Egress safety.** With the query hard-coded, an IMSI/SUPI/internal IP
    can't leak into a third-party API by way of the model pasting a log
    line into a search box.
  - **Positioning.** "It can search the web" is undifferentiated; a
    version/advisory check reads as a network-operations capability.
- Demo scenario it unlocks: `tail_nf_logs("amf")` → startup banner yields
  the running version → release check → "three AMF fixes and one advisory
  have landed since; one matches the NGAP error in your logs." Joins live
  network state to current public knowledge, which nothing in the system
  can do today.
- Human Approval Mode gating: not needed by default. The call is read-only
  and can't touch VM1, and gating it mid-RCA would break the "no text
  between tool calls" flow for no safety gain — the real risk was egress,
  and the hard-coded query shape already addresses it.
- Sequencing: lowest priority of this list. Items 3 and 4 are both
  stronger demo value for comparable effort — item 4's trend reasoning in
  particular is a better autonomy story with the same read-only safety
  profile.
