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
