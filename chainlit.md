# Network Agent

An agentic AI assistant for managing a live **Open5GS 5G core network**.
The agent autonomously chains tool calls to diagnose issues, remediate faults,
and explain network behaviour — all visible as expandable steps in real time.

---

## Available Tools

| Tool | What it does |
|------|-------------|
| `system_health_snapshot` | One-shot health check of all NFs |
| `nf_lifecycle` | Start, stop, restart, or query the status of any Open5GS NF |
| `nf_resource_usage` | CPU/memory usage per NF process |
| `tail_nf_logs` | Read and filter recent log entries from any NF log file |
| `read_nf_config` | Read parsed YAML config for any NF — explorable by subtree path |
| `list_ue_sessions` | List all active UE registrations and their PDU sessions |
| `get_ue_trace` | Capture a UE's call-flow trace and render it as a sequence diagram |
| `amf_ran_query` | Query AMF for connected RAN/gNB info |
| `subscriber` | Create, read, update, or delete subscriber profiles in MongoDB |
| `subscriber_update_profile` | Update a subscriber's profile fields |
| `subscriber_update_slices` | Update a subscriber's network slice assignments |
| `search_knowledge_base` | Semantic search over local Open5GS documentation (RAG) |

---

## Demo Scenarios

Three quick-start buttons appear on every message:

1. **🏥 Health Snapshot** — Poll every network function and get an instant status
   table with 🟢🟡🔴 emojis.

2. **👀 Watch Subscriber Attach** — List all currently registered UEs and their
   active PDU sessions, including assigned IP addresses.

3. **🔍 Debug Attach Failure** — Runs the full root-cause-analysis chain (health →
   logs → config → sessions → subscriber checks) and reports the root cause,
   evidence, and a recommended fix.

You can also toggle **Human Approval Mode** in the ⚙️ chat settings to require
your sign-off before every tool call — useful when demoing lifecycle
operations like restarts.

---

## Call Flow Diagrams

Ask the agent to trace or explain any 5G procedure and it will render a
**Mermaid sequence diagram** inline:

- `show me the 5G registration call flow`
- `draw the PDU session establishment procedure`
- `trace the last attach attempt`
- `what does the authentication flow look like between UE, AMF, and AUSF?`

---

## Example Queries

```
show subscriber imsi-999700000000001
tail amf logs for the last 10 minutes
restart the smf
what is the AMF SBI address?
create 5 subscribers starting from imsi-999700000000010
```
