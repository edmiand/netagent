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

### 1. Vector store for RCA grounding (RAG)
- Small self-hosted vector store (Chroma or pgvector) seeded with Open5GS
  docs, relevant 3GPP spec excerpts, and past RCA reports.
- New `search_knowledge_base` MCP-style tool so RCA answers cite *why* a
  config value is wrong, not just *that* it's wrong.
- Persist past RCA reports (chat history already goes through
  `data_layer.py`) into the same store → episodic memory, "have we seen this
  failure before?" — a strong autonomous-reasoning demo beat.
- No VM1 changes needed. Cheapest item on this list.

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
