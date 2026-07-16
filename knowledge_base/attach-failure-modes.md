# UE Attach Failure Modes

Source: https://open5gs.org/open5gs/docs/troubleshoot/01-simple-issues/
(supplemented with open5gs-nf-overview.md for call-flow staging)

A "subscriber can't attach" report can mean several distinct underlying
problems. Open5GS's own troubleshooting guide groups the most common
real-world issues as follows.

## 1. gNB/eNB connectivity issues (never reaches authentication)

Open5GS's troubleshooting guide flags mismatched **MNC/MCC** between the
gNB/eNB and the AMF/MME's configured `guami`/`gummei` and `tai` MCC/MNC
pair, or a mismatched **Tracking Area Code (TAC)**, as a common cause of
the base station simply failing to connect to the core at all. This
happens before any subscriber-specific authentication is attempted —
fixing it requires editing the AMF (or MME, for LTE) configuration file
to match what the RAN actually advertises.

## 2. Authentication failure

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

## 3. Session establishment failure

**Symptom:** UE successfully registers but has no PDU session.

Open5GS's guide lists **missing or misconfigured DNN/APN configuration**
as a common documented cause — the subscriber's provisioned DNN/APN must
match what the network is actually configured to serve.

## 4. General diagnostic approach (per Open5GS's guide)

- First confirm every core component is actually running (AMF, SMF, UPF,
  AUSF, UDM, UDR, NRF, and for LTE deployments also MME/SGW/PGW/HSS/PCRF).
- Startup failures are usually configuration errors in the YAML files —
  check `/var/log/open5gs/` for the specific NF's log.
- For deeper investigation, Open5GS recommends enabling debug-level
  logging (via the YAML config) and, if filing a GitHub issue, attaching
  packet captures (`.pcapng`), the relevant config files, and logs.

## Quick triage heuristic

| Observation | Likely failure stage |
|---|---|
| gNB never connects to core at all | MCC/MNC/TAC mismatch (stage 1) |
| UE absent from active sessions entirely | Authentication (stage 2) |
| UE registered, no PDU session | DNN/APN or session establishment (stage 3) |
| UE has PDU session, no connectivity | UPF / routing (not detailed in Open5GS's simple-issues guide — check UPF logs directly) |
