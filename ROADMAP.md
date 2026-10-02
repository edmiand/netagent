# Roadmap

Candidate features to extend the "showcase agentic AI value" demo, in
priority order (highest demo payoff for effort first). Memory & Learning
(cross-session incident recall) shipped — see `agent/tools/memory.py` and
the "Memory & Learning" toggle in `app.py`'s settings panel, alongside
Human Approval Mode.

## 1. Dry-run / simulate mode
**Problem:** the only trust mechanism today is Human Approval Mode
(approve/deny with no preview of *what* would change). For lifecycle ops
(`nf_lifecycle`) and subscriber/slice updates, showing a diff before
execution is a stronger trust story than a blind approve/deny prompt.
**Approach:** wrap mutating tools (similar to `agent/approval.py`'s
pattern) so that, when a "Dry Run" toggle is on, the call returns a
computed "would change X → Y" preview instead of executing, and the agent
reports it without acting. Pairs naturally with Human Approval Mode as a
second, complementary trust toggle in the same settings panel.

## 2. Multi-NF correlated RCA scenario
**Problem:** the current "Debug Attach Failure" demo can be solved by
checking one degraded NF. The strongest "the agent actually reasoned"
demo requires a root cause that only becomes visible by correlating
symptoms across 3+ NFs (e.g. AMF timeout ← SMF misconfig ← stale UDR
entry).
**Approach:** likely needs either organic multi-NF fault state or the
fault-injection tool already noted below to reliably reproduce on demand.

## 3. Tiered approval
**Problem:** Human Approval Mode is currently all-or-nothing — every tool
call is gated the same way regardless of blast radius.
**Approach:** extend `agent/approval.py` so read-only tools auto-pass,
mutating tools always gate (current behavior), and destructive tools
(`nf_lifecycle` restart/stop) require a typed confirmation rather than a
single click. Demonstrates thoughtful autonomy design, not just a blanket
switch.

## 4. Confidence + evidence scoring
**Problem:** the RCA report format (Root Cause / Evidence / Recommended
Action) doesn't currently self-assess how confident the conclusion is.
**Approach:** extend `prompts/system.txt`'s RCA step 6 to require a
confidence label (high/medium/low) tied to how directly the evidence
supports the conclusion — cheap prompt-only change, no new tools.

## 5. "Show your reasoning" replay
**Problem:** the reasoning-token toggle (`show_thinking`) exposes raw
model thinking, but there's no compact, human-readable timeline of *which
tools were called in what order and why* after the fact.
**Approach:** a post-RCA summary step (rendered in the Chainlit Steps UI,
similar to the existing "📊 Context" step) that lists the tool-call
sequence — distinct from and complementary to the reasoning-token stream.

## 6. Threshold-based alerting
**Problem:** `nf_resource_usage` is only checked on demand today — the
agent never watches metrics unless asked.
**Approach:** requires a background poller (outside the per-message
Chainlit request/response cycle) that periodically calls
`nf_resource_usage`/`system_health_snapshot` and pushes a Chainlit
notification when a threshold is crossed. Bigger lift than the prompt/tool
-only items above — needs a scheduling mechanism, not just a new tool.

## 7. Scheduled health digest
**Problem:** every demo interaction today is user-initiated; nothing
showcases the agent acting autonomously without a human starting the
conversation.
**Approach:** a cron-triggered agent run producing a daily health-summary
report, delivered outside the chat session (Slack/email). Shares the
scheduling-infrastructure need with item 6 above — worth building
together if either is picked up.

## 8. Natural-language bulk operations
**Problem:** batch asks ("create subscribers 3 through 11") are already
allowed to chain tool calls per `prompts/system.txt`, but there's no demo
scenario that showcases turning a fuzzy, high-level instruction ("move all
subscribers on slice X to slice Y") into a precise multi-call plan.
**Approach:** primarily a demo-scenario/prompt exercise rather than new
tooling — `subscriber` (with `filter`) + `subscriber_update_slices` already
cover the mechanics; needs a worked example and Human Approval Mode
interplay for the batch.

## 9. Notification / ticketing action tools
- Notification tool (Slack webhook or email) the agent calls after RCA to
  "page oncall" — demonstrates closing the loop from diagnosis to action.
  Pairs with Human Approval Mode as a gate before it fires.
- Ticketing tool (Linear/Jira, or a local SQLite `incidents` table) where
  the agent files a structured incident report after RCA.

## 10. Time-series metrics for trend reasoning
- Prometheus + lightweight exporter on VM1, or simpler: scrape
  `nf_resource_usage` on an interval into a local SQLite/TimescaleDB.
- Lets the agent reason over trends instead of point-in-time snapshots
  (e.g. "UPF memory has climbed 40% over the last hour").
- Grafana as a companion dashboard is optional polish, not required for
  the agent itself.

## 11. Fault injection tool
- A `fault_injection` tool wrapping something like UERANSIM (synthetic UE
  attach/detach) or a scripted, reversible config perturbation, so
  failures can be triggered on demand instead of relying on organic
  network state.
- Needs care re: "Do not modify anything on VM1" constraint — likely needs
  to be an additive/reversible tool rather than a direct config edit, or
  requires explicit sign-off to relax that constraint for a sandboxed
  fault path.

## 12. Multi-agent orchestration (supervisor pattern)
- Replace the single `create_react_agent` in `agent/graph.py` with a
  supervisor routing to specialized agents (RCA agent, subscriber-mgmt
  agent, query/reporting agent), each with its own short prompt and tool
  subset.
- Arguably the single highest-leverage "agentic AI" demo item — visibly
  showcases autonomy/delegation across specialized subagents in a way a
  single ReAct loop can't — but the biggest lift of everything on this
  list. Revisit after cheaper items above are in place.

## 13. Image-based emergency detection + UE broadcast
**Problem:** the agent only takes text. An operator who has a photo of an
incident site (fire, flood, structural damage, medical event) has no way to
feed it in, and there's no path from "this looks like an emergency" to
"every subscriber on the network is told".
**Approach:** operator drops an image into the chat → a dedicated vision
triage step classifies it → if it's an emergency, after one operator
confirmation, an alert is sent to every UE with an active PDU session via
the existing `send_ue_notification` MCP tool. "Connected users" means
**UEs on the 5G network**, not other web-UI sessions: Chainlit has no
built-in cross-session broadcast, and everyone logs in as the same `demo`
user (`app.py`'s `_header_auth`), so web-UI broadcast is out of scope.

**Changes required:**
- **Upload intake (`app.py`, `start.py`).** `spontaneous_file_upload` is
  already enabled but with `accept = ["*/*"]` and a 500 MB limit. Narrow it
  to `image/*` and about 10 MB from `start.py`'s config sync (same pattern
  as branding), since `.chainlit/config.toml` must not be hand-written.
  `on_message` currently passes only `message.content` and drops
  `message.elements`. Read the image elements and base64-encode them, then
  build a multimodal `HumanMessage` (`image_url` content blocks).
  `_run_agent(user_input: str)` needs to accept content blocks.
- **Keep base64 out of history.** The `MemorySaver` checkpointer would
  re-send the image on every later turn. After triage, swap the image for
  its text verdict before it goes to the main agent. Check that uploaded
  images show up on thread resume (`data_layer.py`'s `_LocalStorageClient`
  already stores elements).
- **Vision model (`config/models.yaml`, `agent/llm.py`).** None of the
  current entries is confirmed vision-capable (gpt-oss is text-only;
  check gemma4 / nemotron on ollama.com). Add a dedicated `vision:` block
  (like `embeddings:`) so triage doesn't depend on which chat model is
  picked in ⚙️ Settings, plus a `get_vision_llm()` helper. Privacy: a
  `-cloud` model sends the photo to Ollama Cloud; a local vision model
  avoids that but costs RAM. Decide before picking.
- **Triage classifier (new `agent/tools/image_triage.py` +
  `prompts/image_triage.txt`).** A fixed classification call, not a ReAct
  decision. It returns structured output
  `{emergency, category, confidence, summary}`, and a confidence threshold
  lives in config. **Prompt-injection guard:** text in the image ("ignore
  instructions, notify everyone…") must not reach the UE message. The
  broadcast text comes from a template filled from `category`/`summary`,
  not from free text the model writes.
- **Broadcast fan-out (new module, called from `app.py`).** Get targets from
  `list_ue_sessions` (IMSIs with an active IPv4 PDU session). Then **one
  required aggregate approval** (regardless of the Human Approval toggle).
  It shows the image, the verdict, the message text and the recipient count.
  After that, call the existing `send_ue_notification` MCP tool once per
  UE directly from code (concurrent, with a cap on parallel sends). This
  avoids N separate `agent/approval.py` dialogs and N LLM tool calls, and
  keeps the "one call per UE" rule. Don't add a local send tool (CLAUDE.md
  forbids it). Nothing changes on VM1: the payload stays
  `{message, incident_id}`, so urgency is a text prefix (`🚨 EMERGENCY:`)
  within the 500-char limit. Generate an `incident_id` per image. Report a
  delivery summary table using the tool's `reason` codes (`no_session`,
  `connection_refused`, `timeout`).
- **Policy / prompt.** `knowledge_base/ue-incident-notifications.md`
  currently allows notifying only *after a verified fix* and only
  *affected* UEs. Add an "Emergency broadcast" section as an explicit
  exception, and align `prompts/system.txt`'s notification rule. Rebuild
  the KB (`scripts/build_knowledge_base.py`) and restart the app.
- **Guardrails.** One broadcast per image, plus a cooldown so the same scene
  uploaded again doesn't re-alert everyone. Keep an audit record (uploader,
  verdict, approver, recipients, results); `agent/tools/memory.py`'s
  incident store may be the natural home. Add a follow-up "all clear" /
  correction broadcast.
- **Tests / docs.** Unit tests for triage with sample images (emergency,
  benign, injected text), and a fan-out test with a fake MCP tool. Add a
  4th check to `test_integration.py` (vision model reachable). Update
  CLAUDE.md (new paths, `vision:` block, broadcast exception to the
  one-call-per-UE/approval rule) and README.

**Open decisions before coding:**
- Which vision model (cloud vs local, given privacy).
- Is the broadcast approval always required (recommended), or only when
  Human Approval Mode is on?

**Rough size:** medium overall. The biggest risks are vision-model
availability on Ollama, false positives alerting every subscriber (hence
the required approval), and photos leaving the machine via cloud models.
