# Demo: tamper-evident audit trail for an AI network agent

**Message in one line:** every change NetAgent's AI makes to the live 5G core leaves a
record that NetAgent itself cannot edit — and anyone can check it.

Runtime: ~7 minutes · Network: Hedera **testnet** · Background: [HEDERA.md](HEDERA.md)

---

## Why it matters (talking points)

| Value | What the audience sees |
|---|---|
| **Accountability for an AI with write access** | Every restart, subscriber change or UE notification leaves a timestamped entry — without anyone asking for it. |
| **Records NetAgent can't alter** | Entries live on Hedera, not in NetAgent's database or log files. They can't be quietly edited or deleted, and anyone can verify them on HashScan without trusting NetAgent. |
| **Reliable timing and order** | The network stamps each entry with its consensus timestamp — proof of *when* and *in what order*. |
| **Two separate controls** | Human Approval Mode controls *what* happens; the ledger proves *that* it happened. |
| **Privacy built in** | Entries are one-line summaries with no personal data, and the tool itself refuses IMSIs and IP addresses even if the model slips. |
| **Cheap and fast** | ~0.6s to write, ~2–4s until publicly visible. Testnet: topic + 5 messages ≈ 0.22 HBAR. Mainnet: a fraction of a cent per message (check Hedera's current fee schedule before quoting a number). |

---

## Before you start

- [ ] App running (`./netagent.sh status`), VM1 MCP server reachable, a UE attached.
- [ ] `config/hedera.yaml` → `enabled: true`; `HEDERA_OPERATOR_ID` / `HEDERA_OPERATOR_KEY` in `.env`.
- [ ] **Fresh topic** (recommended): the current topic `0.0.10994808` already holds test
      messages. Create a new one and put its ID in `config/hedera.yaml` so HashScan opens clean.
- [ ] Open a **new chat** (the system prompt is read when a chat starts).
- [ ] ⚙️ Settings → **Human Approval Mode: on**.
- [ ] Second browser tab: `https://hashscan.io/testnet/topic/<topic_id>`.
- [ ] Fault for scene 4 prepared (see below).
- [ ] **Rehearse once end to end** — every entry is public and permanent.
- [ ] Note the sequence numbers you expect, so scene 6 can name one.

---

## Script

### 1. The problem — 30s

> "This AI agent can restart parts of a live 5G core. If something breaks at 3am, how do
> you prove what it did, and when? Its own logs aren't good enough — the same system that
> acted would be vouching for itself."

### 2. A change, with approval and a record — 2 min

**Type:** `Restart the NSSF.`

> Use NSSF or BSF. **Do not** restart AMF, SMF or UPF — that drops every UE session.

1. Approval prompt for the restart → **Approve**.
2. A second approval prompt appears: the audit-trail write → **Approve**.

> "Nobody asked it to record anything. The agent's rules say: after any successful change,
> write one line to the ledger. And I still approved it — two separate controls."

Expected entry, roughly: `NF restart — NSSF — running again`

### 3. Check it outside NetAgent — 1 min

Switch to the HashScan tab and refresh (wait ~3s — the mirror node lags consensus slightly;
talk through it).

> "This isn't our database. It's a public ledger. Anyone — an auditor, a partner, a
> regulator — can open this page and see the same entry with the same timestamp."

Point at: the message text, the consensus timestamp, the sequence number.

### 4. An investigation gets recorded — 2 min

**Prepare beforehand:** a known fault, e.g. bar a test subscriber (subscriber status = 1)
so its UE can't attach. If you ask the agent to do it, that change is audited too — which
is fine, and a good aside.

**Click:** 🔍 **Debug Attach Failure** (approve each tool call as it comes).

> "It investigates on its own — health, logs, config, subscriber — finds the root cause,
> and because it reached a confident conclusion, records a one-line summary of it."

Refresh HashScan to show the new entry.

**Then click:** 🔏 **Fingerprint report** (under the report). NetAgent hashes the exact
report text, saves a copy, and records the SHA-256 on the ledger. Note the entry number.

> "The full report stays private on our server — only its fingerprint goes on the public
> ledger. But that fingerprint pins down every character of it."

Undo the fault afterwards.

### 5. The privacy guard — 30s

**Type:** `Record on the audit trail: UE 10.45.0.2 recovered.`

The tool refuses — the message contains an IP address.

> "The ledger is public and permanent, so the tool itself blocks IMSIs and IP addresses.
> Even if the model gets it wrong, sensitive data can't land on-chain."

### 6. Contrast with ordinary logs — 1 min

> "Our own logs and chat history are files on a server. An admin — or a compromised
> agent — could edit or delete them."

**Click:** 📜 **Audit Trail** → approve. Everything from this demo, newest first, with
times and a HashScan link.

**Type:** `Verify report entry <N>` (the fingerprint from scene 4) → ✅ verified.

Now play the insider: open the saved copy (path shown when you fingerprinted it, under
`data/reports/`) and change one word — e.g. the root cause. Save.

**Type:** `Verify report entry <N>` again → ❌ **does not match**; the hashes differ.

> "One changed word, and the ledger catches it. Whoever edited the file can't edit the
> ledger."

Put the original word back afterwards (verification passes again), or the report stays
flagged.

### Close — 15s

> "Human approval decides what the AI may do. The ledger proves what it actually did —
> cheaply, in seconds, verifiable by anyone."

---

## If something goes wrong

| Symptom | Cause / fix |
|---|---|
| Read-back says `found: false` | Mirror node hasn't indexed it yet. Ask again after a few seconds. |
| Second approval prompt never appears | Restart failed → no entry, by design. Show that as a feature: failed actions aren't recorded as done. |
| Entry never written, no prompt | Chat started before the prompt rule loaded, or `enabled: false`. Open a new chat. |
| Approval prompt vanished | 120s timeout auto-denies, and a page reload drops the pending call. Repeat the request. |
| Chat start fails with `ConnectError` | VM1's MCP server unreachable — not Hedera. Check VM1, refresh. |
| `not configured` error | `HEDERA_*` variables missing from `.env`. |
| No 🔏 button under the report | The reply lacked the `**Root cause:**` heading (e.g. inconclusive RCA). Re-run, or skip the fingerprint beats. |
| Verify says the saved copy is missing | The file under `data/reports/` was deleted or renamed — it must keep its `<sha256>.md` name. |

---

## What's behind each beat

| Beat | Mechanism |
|---|---|
| Automatic entry after a change | System-prompt audit rule + `hcs_submit_message` |
| HashScan links | `explorer_base_url` in `config/hedera.yaml` |
| 📜 Audit Trail button | `hcs_list_recent` (mirror node, newest first) |
| 🔏 Fingerprint report | `app.py` callback → `fingerprint_report()`: SHA-256 in code, copy in `data/reports/` |
| Tamper check | `hcs_verify_report`: re-hash the saved copy, compare with the ledger |
| Privacy refusal | IMSI/IPv4 check inside `hcs_submit_message` |
