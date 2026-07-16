# Reading Open5GS Logs and Configs During Diagnosis

Source: https://open5gs.org/open5gs/docs/troubleshoot/01-simple-issues/

## Open5GS's documented general diagnostic approach

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

## Enabling deeper diagnostics

Open5GS's guide recommends enabling debug-level logging by editing the
relevant NF's YAML configuration when the default log level doesn't
surface enough detail to diagnose an issue.

## Escalation path (per Open5GS's docs)

If simple-issue diagnosis doesn't resolve the problem, Open5GS's guide
directs users to file a GitHub issue, and recommends including packet
captures (`.pcapng` files), the relevant configuration files, and logs —
i.e., the same three artifact types (config, logs, packet-level
evidence) that this app's own RCA workflow gathers (health check → logs
→ config), minus packet captures which aren't exposed via this app's
current MCP tools.

## General principle

A log error is a symptom; the config or subscriber-profile value it
traces back to is the root cause. Prefer citing the specific documented
error signature (e.g. `Authentication failure(MAC failure)`) plus the
config/profile value responsible, over a vague description like "a
misconfiguration."
