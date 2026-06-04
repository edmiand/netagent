# 5G Core Agent

An agentic AI assistant for managing a live **Open5GS 5G core network**.
The agent autonomously chains tool calls to diagnose issues, remediate faults,
and explain network behaviour — all visible as expandable steps in real time.

---

## Available Tools

| Tool | What it does |
|------|-------------|
| `nf_lifecycle` | Start, stop, restart, or query the status of any Open5GS network function |
| `system_health_snapshot` | One-shot health check of all NFs, MongoDB, and the TUN device |
| `subscriber_crud` | Create, read, update, or delete subscriber profiles in MongoDB |
| `list_ue_sessions` | List all active UE registrations and their PDU sessions |
| `tail_nf_logs` | Read and filter recent log entries from any NF log file |

---

## Demo Scenarios

1. **Health Snapshot** — Poll every network function and get an instant summary
   of which are healthy, degraded, or down.

2. **Watch Subscriber Attach** — List all currently registered UEs and their
   active PDU sessions, including assigned IP addresses.

3. **Debug Attach Failure** — A subscriber can't attach. The agent runs a health
   snapshot, tails the degraded NF's logs, identifies the root cause, restarts
   the NF, verifies recovery, and renders a Mermaid sequence diagram of the
   full attach procedure.
