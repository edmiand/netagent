# Notifying UEs About Incident Changes

Source: NetAgent operational policy (project-internal, not Open5GS
documentation). Delivery mechanics are described by the UE notification
tool's own MCP description on VM1; the UE-side receiver is
scripts/ue_notify_listener.py in the NetAgent repo.

## What a UE notification is

The core can push a short text message to a specific subscriber's device
over that UE's own 5G data session. The tool resolves the IMSI to the UE's
current PDU session IPv4 address and POSTs `{"message", "incident_id"}` to
`http://<ue_ip>:9000/notify`. On the UE side, a listener bound to the UE's
tunnel interface (e.g. `uesimtun0`) prints each message for the responder
using that device.

## When to notify a UE

Notify only **after an incident-related change has been applied and
verified** — never before, and never speculatively:

1. A fix for an incident has actually been applied (e.g. an NF restarted, a
   subscriber profile or slice assignment corrected, a barred subscriber
   unbarred).
2. The change has been **verified with live data** — for example the NF
   reports healthy, or the affected UE shows a registration and an active PDU
   session again.
3. Only then, send **one short message per affected responder** (one UE per
   affected IMSI) stating what changed.

Do not notify:

- During an investigation or RCA, before any change is made.
- When a change failed, was denied, or could not be verified — report that to
  the operator instead.
- UEs that were not affected by the incident.
- Repeatedly for the same change — one message per UE per change.

## What the message should say

- One or two plain-English sentences, well under the 500-character limit.
- State what changed and the current state, e.g. "SMF was restarted at 14:05;
  data sessions are restored. Reconnect if you still have no data."
- Pass the incident identifier as `incident_id` when one exists, so deliveries
  can be correlated with the incident record.
- No raw JSON, log lines, credentials (K/OPc), or internal IP addresses.

## Write-action rules

Sending a notification is a **write action** with an external effect on the
subscriber's device:

- Make **exactly one notification call per UE**. When several UEs are
  affected, send them as separate calls — one per IMSI — and report a
  combined delivery summary at the end.
- When Human Approval Mode is on, each notification call is shown to the
  operator for approval before it is sent, like every other tool call. A
  denied notification must not be retried.

## Reading the result

- `ok: true` — delivered; the result includes `ue_ip`, `http_status` and
  `round_trip_ms`.
- `reason: "no_session"` — the UE has no active PDU session with an IPv4
  address, so there is no path to it. Verify the UE is attached first.
- `reason: "connection_refused"` — the UE is reachable but no listener is
  running on that port; the responder needs to start
  `scripts/ue_notify_listener.py` on the UE host.
- `reason: "timeout"` / `"request_error"` — the data path to the UE is not
  working end to end (UPF, routing, or the UE's tunnel); treat this as a
  connectivity symptom, not a delivered notification.
