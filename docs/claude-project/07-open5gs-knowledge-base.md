# NetAgent — Open5GS knowledge base (the agent's RAG documents)

> Project knowledge file 7 of 7 · snapshot as of 2026-11-04 (commit 9d501a7).
> The documents behind the agent's `search_knowledge_base` tool, merged into one file. Each
> cites its official Open5GS documentation source, except the UE incident-notification
> policy, which is NetAgent's own operating policy. Headings are one level lower than in the
> originals (`knowledge_base/<name>.md`).

---

<!-- source file: knowledge_base/attach-failure-modes.md -->
## UE Attach Failure Modes

Source: https://open5gs.org/open5gs/docs/troubleshoot/01-simple-issues/
(supplemented with open5gs-nf-overview.md for call-flow staging)

A "subscriber can't attach" report can mean several distinct underlying
problems. Open5GS's own troubleshooting guide groups the most common
real-world issues as follows.

### 1. gNB/eNB connectivity issues (never reaches authentication)

Open5GS's troubleshooting guide flags mismatched **MNC/MCC** between the
gNB/eNB and the AMF/MME's configured `guami`/`gummei` and `tai` MCC/MNC
pair, or a mismatched **Tracking Area Code (TAC)**, as a common cause of
the base station simply failing to connect to the core at all. This
happens before any subscriber-specific authentication is attempted —
fixing it requires editing the AMF (or MME, for LTE) configuration file
to match what the RAN actually advertises.

### 2. Authentication failure

**Symptom:** UE never appears in the active session list — no
registration record, no PDU session.

Open5GS's guide states plainly that NR/LTE requires "Mutual
Authentication of both the network and the subscriber," meaning the
USIM's credentials must match what's stored in UDM/UDR (or HSS, on the
LTE side). The documented failure signatures are:

- **Missing IMSI** — logs show an error like `Cannot find IMSI in DB :
  001000000000001`, meaning the subscriber simply doesn't exist in the
  subscriber database at all.
- **Credential mismatch** — logs show `Authentication failure(MAC
  failure)`, meaning the subscriber exists but the K/OPc values programmed
  into the USIM don't match what's stored for that subscriber, so the
  authentication vector's MAC (Message Authentication Code) check fails.

### 3. Session establishment failure

**Symptom:** UE successfully registers but has no PDU session.

Open5GS's guide lists **missing or misconfigured DNN/APN configuration**
as a common documented cause — the subscriber's provisioned DNN/APN must
match what the network is actually configured to serve.

### 4. General diagnostic approach (per Open5GS's guide)

- First confirm every core component is actually running (AMF, SMF, UPF,
  AUSF, UDM, UDR, NRF, and for LTE deployments also MME/SGW/PGW/HSS/PCRF).
- Startup failures are usually configuration errors in the YAML files —
  check `/var/log/open5gs/` for the specific NF's log.
- For deeper investigation, Open5GS recommends enabling debug-level
  logging (via the YAML config) and, if filing a GitHub issue, attaching
  packet captures (`.pcapng`), the relevant config files, and logs.

### Quick triage heuristic

| Observation | Likely failure stage |
|---|---|
| gNB never connects to core at all | MCC/MNC/TAC mismatch (stage 1) |
| UE absent from active sessions entirely | Authentication (stage 2) |
| UE registered, no PDU session | DNN/APN or session establishment (stage 3) |
| UE has PDU session, no connectivity | UPF / routing (not detailed in Open5GS's simple-issues guide — check UPF logs directly) |

---

<!-- source file: knowledge_base/open5gs-logs-and-configs.md -->
## Reading Open5GS Logs and Configs During Diagnosis

Source: https://open5gs.org/open5gs/docs/troubleshoot/01-simple-issues/

### Open5GS's documented general diagnostic approach

1. **Confirm all components are running.** Open5GS's guide explicitly
   lists checking that MME, SGW-C, SMF, AMF, SGW-U, UPF, HSS, PCRF, NRF,
   and other configured components are actually up before investigating
   further.
2. **Check logs for startup/config errors.** Startup failures are
   attributed to configuration errors in the per-NF YAML files; the guide
   directs users to `/var/log/open5gs/` to find the specific error for
   the NF that failed to start.
3. **Check MCC/MNC/TAC alignment for RAN connectivity issues.** If a
   gNB/eNB won't connect to the core, the guide points to mismatched
   MNC/MCC between the RAN and the AMF/MME's `guami`/`gummei`/`tai`
   configuration, or a mismatched Tracking Area Code — both are config
   file issues, not subscriber-side issues.
4. **Check authentication-specific log signatures.** `Cannot find IMSI in
   DB : <imsi>` means the subscriber record doesn't exist; `Authentication
   failure(MAC failure)` means the subscriber exists but K/OPc don't
   match. Both come from AMF/AUSF logs during the authentication step.
5. **Check DNN/APN configuration** when session establishment fails —
   the guide names missing/misconfigured DNN/APN as a common issue.

### Enabling deeper diagnostics

Open5GS's guide recommends enabling debug-level logging by editing the
relevant NF's YAML configuration when the default log level doesn't
surface enough detail to diagnose an issue.

### Escalation path (per Open5GS's docs)

If simple-issue diagnosis doesn't resolve the problem, Open5GS's guide
directs users to file a GitHub issue, and recommends including packet
captures (`.pcapng` files), the relevant configuration files, and logs —
i.e., the same three artifact types (config, logs, packet-level
evidence) that this app's own RCA workflow gathers (health check → logs
→ config), minus packet captures which aren't exposed via this app's
current MCP tools.

### General principle

A log error is a symptom; the config or subscriber-profile value it
traces back to is the root cause. Prefer citing the specific documented
error signature (e.g. `Authentication failure(MAC failure)`) plus the
config/profile value responsible, over a vague description like "a
misconfiguration."

---

<!-- source file: knowledge_base/open5gs-nf-overview.md -->
## Open5GS Network Function Overview

Source: https://open5gs.org/open5gs/docs/guide/01-quickstart/
(supplemented with https://open5gs.org/open5gs/docs/tutorial/01-your-first-lte
for LTE-side terminology mapping)

Open5GS implements a Service Based Architecture (SBA) for the 5G
Standalone (SA) core — a set of independent network functions (NFs) that
register with and discover each other dynamically, rather than being
wired together with static point-to-point connections the way 4G EPC
components (MME/SGW/PGW) traditionally are.

### Core NFs and their roles (per Open5GS's own quickstart guide)

- **AMF (Access and Mobility Management Function)** — handles connection
  and mobility management. Serves as the entry point where gNBs (5G base
  stations) connect. Open5GS describes it as covering "a subset of what
  the 4G MME is tasked with."
- **SMF (Session Management Function)** — manages all session-related
  operations. Open5GS notes this consolidates responsibilities that were
  previously split across 4G's MME, SGW-C, and PGW-C into one component.
- **UPF (User Plane Function)** — the sole user-plane element. It carries
  user data packets between the gNB and the external WAN, and connects
  back to the SMF for control (PFCP).
- **AUSF, UDM, and UDR** — described by Open5GS as together carrying out
  what the 4G HSS did: generating SIM authentication vectors (AUSF) and
  holding/mediating the subscriber profile (UDM/UDR).
- **NRF (NF Repository Function)** — control-plane functions register
  with the NRF, which then helps them discover each other. This
  registration-based discovery model is what replaces 4G's static,
  point-to-point NF connectivity.
- **PCF (Policy Control Function)** — handles charging and enforcing
  subscriber policies.
- **NSSF (Network Slice Selection Function)** — provides the mechanism
  for selecting a network slice.
- **BSF and SEPP** — BSF provides binding support (tracking which PCF
  instance is bound to a given session); SEPP provides roaming security
  capabilities (relevant to inter-operator roaming scenarios, not covered
  in Open5GS's core quickstart tutorial).

### LTE-side terminology mapping (for reference)

Open5GS also supports 4G/LTE deployments, where the equivalent roles are
split differently: MME (mobility + auth), HSS/UDR (subscriber storage),
and SGW/PGW (user-plane routing, now unified into UPF on the 5G SA side).
Subscriber provisioning in the LTE tutorial uses the same underlying
credential fields (IMSI, K, OPc) that carry over to 5G SA subscriber
profiles.

### Typical attach call flow (Open5GS SBA)

1. UE → AMF: registration request (via gNB).
2. AMF → AUSF: authentication using subscriber's K/OPc (retrieved via
   UDM/UDR).
3. AMF → UDM: retrieve subscription data.
4. AMF → SMF: PDU session establishment request.
5. SMF → UPF: session rules over PFCP (N4); UPF becomes active on the
   user-plane path.

A break at any step surfaces differently — authentication failures never
get past step 2, session failures happen after registration but before
step 5, and connectivity issues can occur even after step 5 completes
successfully (UPF up but misrouting traffic).

---

<!-- source file: knowledge_base/snssai-and-slicing.md -->
## S-NSSAI and Network Slicing

Sources:
- https://open5gs.org/open5gs/docs/guide/01-quickstart/ (NSSF's role)
- https://open5gs.org/open5gs/docs/tutorial/07-infoAPI-UE-gNB-session-data/ (S-NSSAI as a runtime field)
- General 3GPP terminology (SST/SD numeric meaning) — NOT documented in
  Open5GS's own docs as fetched; included here as widely-used standard
  background, flagged separately from the Open5GS-specific material above.

### What Open5GS's own docs say

Per Open5GS's quickstart guide, the **NSSF (Network Slice Selection
Function)** "provides a way to select the network slice" — it is the NF
responsible for slice selection, but the quickstart guide does not
elaborate on S-NSSAI's internal SST/SD structure.

Per the infoAPI tutorial, **S-NSSAI** is one of the fields exposed for a
connected UE via the AMF's `/ue-info` endpoint and for its PDU sessions
via the SMF's `/pdu-info` endpoint — i.e., the subscriber's active slice
assignment can be inspected directly at runtime through this API, which
is a useful diagnostic tool independent of reading MongoDB or config
files directly.

### Supplementary 3GPP background (not Open5GS-doc-sourced)

S-NSSAI has two parts:
- **SST (Slice/Service Type)** — standardized numeric categories exist
  (1 = eMBB, 2 = URLLC, 3 = MIoT), with operator-defined values also
  possible in non-standardized ranges.
- **SD (Slice Differentiator)** — an optional operator-assigned value
  distinguishing multiple slices sharing the same SST.

### Practical diagnostic implication

Because S-NSSAI is directly queryable via the infoAPI at runtime, a slice
mismatch between what a subscriber is assigned and what the gNB/AMF
actually serves can be confirmed by comparing the infoAPI's reported
S-NSSAI for that UE against the AMF/gNB's configured/advertised slice
list, rather than only inferring it from failure symptoms.

---

<!-- source file: knowledge_base/subscriber-profile-fields.md -->
## Subscriber Profile Fields

Sources:
- https://open5gs.org/open5gs/docs/tutorial/01-your-first-lte/ (provisioning fields)
- https://open5gs.org/open5gs/docs/tutorial/07-infoAPI-UE-gNB-session-data/ (fields exposed at runtime)

### Provisioning fields (per the "Your First LTE" tutorial)

Open5GS's tutorial demonstrates two provisioning methods — programming a
physical USIM via PySIM, or adding a subscriber through the Open5GS Web
UI (default `localhost:9999`). Both require the same core fields:

- **IMSI** — the subscriber's unique identifier (example from the
  tutorial: `310789012345301`).
- **K (subscriber key)** — referred to in the tutorial as "Ki," the
  authentication key shared between the USIM and the network.
- **OPc (operator cipher key)** — operator-specific key material combined
  with K during authentication. The tutorial's Web UI method groups K,
  OPc, and AMF (the 3GPP "Authentication Management Field," not the AMF
  network function — an unrelated same-named field) together under
  "security context."
- **APN/DNN** — the data network the subscriber is provisioned to reach.
  On the 5G SA side this is the DNN (Data Network Name); the LTE tutorial
  uses the older APN terminology for the same concept.

A missing or mismatched K/OPc is what produces the `Authentication
failure(MAC failure)` documented in Open5GS's troubleshooting guide (see
attach-failure-modes.md); a missing IMSI record produces `Cannot find
IMSI in DB`.

### Runtime fields (per the infoAPI tutorial)

Open5GS exposes a lightweight HTTP infoAPI (default port 9090) for
inspecting live subscriber/session state. The AMF's `/ue-info` endpoint
and SMF's `/pdu-info` endpoint expose, per the tutorial's documented
field list:

- Security credentials and encryption/integrity algorithm state
- **S-NSSAI** (network slice assignment)
- **AMBR** (Aggregate Maximum Bit Rate) limits
- **DNN** and assigned IP address
- QoS flow identifiers and PDU/session state
- Location info, GUTI/TMSI identifiers

This means the same fields that matter for provisioning (DNN, slice,
AMBR, security credentials) are also directly queryable at runtime via
the infoAPI — useful for confirming what a subscriber actually has in
effect versus what was intended, without needing direct MongoDB access.

### Status field

Open5GS's own tutorial/troubleshooting docs (as fetched) do not
separately document a numeric `status` field's allowed/barred semantics
in detail — this project's convention (status 0 = allowed, 1 = barred,
per this app's system prompt) should be treated as this deployment's
documented behavior rather than something independently verified against
Open5GS's public docs.

---

<!-- source file: knowledge_base/ue-incident-notifications.md -->
## Notifying UEs About Incident Changes

Source: NetAgent operational policy (project-internal, not Open5GS
documentation). Delivery mechanics are described by the UE notification
tool's own MCP description on VM1; the UE-side receiver is
scripts/ue_notify_listener.py in the NetAgent repo.

### What a UE notification is

The core can push a short text message to a specific subscriber's device
over that UE's own 5G data session. The tool resolves the IMSI to the UE's
current PDU session IPv4 address and POSTs `{"message", "incident_id"}` to
`http://<ue_ip>:9000/notify`. On the UE side, a listener bound to the UE's
tunnel interface (e.g. `uesimtun0`) prints each message for the responder
using that device.

### When to notify a UE

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

### What the message should say

- One or two plain-English sentences, well under the 500-character limit.
- State what changed and the current state, e.g. "SMF was restarted at 14:05;
  data sessions are restored. Reconnect if you still have no data."
- Pass the incident identifier as `incident_id` when one exists, so deliveries
  can be correlated with the incident record.
- No raw JSON, log lines, credentials (K/OPc), or internal IP addresses.

### Write-action rules

Sending a notification is a **write action** with an external effect on the
subscriber's device:

- Make **exactly one notification call per UE**. When several UEs are
  affected, send them as separate calls — one per IMSI — and report a
  combined delivery summary at the end.
- When Human Approval Mode is on, each notification call is shown to the
  operator for approval before it is sent, like every other tool call. A
  denied notification must not be retried.

### Reading the result

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

