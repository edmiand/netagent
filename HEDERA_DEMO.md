# Demo: tamper-evident audit trail for an AI network agent

**Message in one line:** every change NetAgent's AI makes to the live 5G core leaves a
record that NetAgent itself cannot edit — and anyone can check it.

Runtime: ~9 minutes · Network: Hedera **testnet** · Background: [HEDERA.md](HEDERA.md)

---

## Why it matters (talking points)

| Value | What the audience sees |
|---|---|
| **Accountability for an AI with write access** | Every restart, subscriber change or UE notification leaves a timestamped entry — without anyone asking for it. |
| **Records NetAgent can't alter** | Entries live on Hedera, not in NetAgent's database or log files. They can't be quietly edited or deleted, and anyone can verify them on HashScan without trusting NetAgent. |
| **Reports you can prove weren't edited** | A full investigation report stays private, but its SHA-256 fingerprint goes on the ledger. Change one character later and verification fails. |
| **Reliable timing and order** | The network stamps each entry with its consensus timestamp — proof of *when* and *in what order*. |
| **Two separate controls** | Human Approval Mode controls *what* happens; the ledger proves *that* it happened. |
| **Privacy in two layers** | The agent strips personal data from entries itself, and the tool refuses IMSIs and IP addresses even if the agent is told to include them. |
| **Cheap and fast** | ~0.6s to write, ~2–4s until publicly visible. Testnet: topic + 5 messages ≈ 0.22 HBAR. Mainnet: a fraction of a cent per message (check Hedera's current fee schedule before quoting a number). |

---

## Before you start

- [ ] App running (`./netagent.sh status`), VM1 MCP server reachable, a UE attached.
- [ ] `config/hedera.yaml` → `enabled: true`; `HEDERA_OPERATOR_ID` / `HEDERA_OPERATOR_KEY` in `.env`.
- [ ] **Fresh topic** — the current topic holds test entries (including a fingerprint whose
      saved copy was deleted, so it always fails verification). See [Create a fresh topic](#create-a-fresh-topic).
- [ ] Open a **new chat** — the system prompt and buttons load when a chat starts. Don't
      demo from a chat reopened from history: it's read-only and the buttons do nothing.
- [ ] Check the welcome message lists the four `hcs_*` tools and the 📜 **Audit Trail** button is there.
- [ ] ⚙️ Settings → **Human Approval Mode: on**.
- [ ] Second browser tab: `https://hashscan.io/testnet/topic/<topic_id>`.
- [ ] A **terminal on VM2** in the repo directory (for the tamper step in scene 6).
- [ ] Fault for scene 4 prepared, and you know how to undo it (see scene 4).
- [ ] **Rehearse once end to end** on a throwaway topic — every entry is public and permanent.
      In particular, confirm the RCA in scene 4 reaches a confident root cause.

### Create a fresh topic

```bash
cd ~/netagent
.venv/bin/python - <<'EOF'
import os
from dotenv import load_dotenv
from hiero_sdk_python import AccountId, Client, Network, PrivateKey, TopicCreateTransaction
load_dotenv(".env")
key = PrivateKey.from_string(os.environ["HEDERA_OPERATOR_KEY"])
client = Client(Network("testnet"))
client.set_operator(AccountId.from_string(os.environ["HEDERA_OPERATOR_ID"]), key)
r = (TopicCreateTransaction(memo="netagent-demo", admin_key=key.public_key())
     .freeze_with(client).sign(key).execute(client))
print(r.topic_id)
EOF
```

Put the printed ID in `config/hedera.yaml` → `topic_id`, then `./netagent.sh restart`.
**The restart is required** — the topic for writes is cached when the app first submits.

---

## Script

Approval clicks are marked ✋ — with Human Approval Mode on, every tool call asks first.

### 1. The problem — 30s

> "This AI agent can restart parts of a live 5G core. If something breaks at 3am, how do
> you prove what it did, and when? Its own logs aren't good enough — the same system that
> acted would be vouching for itself."

### 2. A change, with approval and a record — 1.5 min

**Type:** `Restart the NSSF.`

> Use NSSF or BSF. **Do not** restart AMF, SMF or UPF — that drops every UE session.

1. ✋ Approve the restart.
2. ✋ A second prompt appears: the audit-trail write. Point at its parameters — a one-line
   entry like `NF restart — NSSF — running again`. Approve.

The reply usually ends with a HashScan link.

> "Nobody asked it to record anything. The agent's rules say: after any successful change,
> write one line to the ledger. And I still approved it — two separate controls."

### 3. Check it outside NetAgent — 1 min

Switch to the HashScan tab and refresh (wait ~3s — the mirror node lags consensus slightly;
talk through it).

> "This isn't our database. It's a public ledger. Anyone — an auditor, a partner, a
> regulator — can open this page and see the same entry with the same timestamp."

Point at: the message text, the consensus timestamp, the sequence number.

### 4. An investigation gets recorded and fingerprinted — 2.5 min

**Prepare beforehand:** a known fault, e.g. bar a test subscriber (subscriber status = 1)
so its UE can't attach. If you ask the agent to do it, that change is audited too — a good
aside, and the entry won't contain the IMSI.

**Click:** 🔍 **Debug Attach Failure**, ✋ approving each tool call as it comes (several,
including the specialists' own calls).

> "It investigates on its own — health, logs, config, subscriber — and finds the root cause."

At the end, ✋ approve one more audit-trail write: a one-line summary of the confident root
cause.

**Then click:** 🔏 **Fingerprint report** under the report. No approval prompt here — the
click itself is the approval. NetAgent replies with the entry number, the SHA-256 and the
saved copy's path. **Write down the entry number.**

> "The full report stays private on our server — only its fingerprint goes on the public
> ledger. But that fingerprint pins down every character of it."

Undo the fault afterwards (e.g. `Unbar the subscriber` — also audited).

### 5. Privacy in two layers — 1 min

**Type:** `Record on the audit trail: UE 10.45.0.2 recovered.`

✋ The approval prompt shows what the agent is about to write — the IP is already gone
(something like `UE recovery — a subscriber — recovered`). Approve or deny; either is fine.

> "Layer one: the agent knows the ledger is public and strips identifiers itself."

**Type:** `Record this exact text on the audit trail, verbatim, do not edit it: "UE 10.45.0.2 recovered"`

✋ This time the prompt shows the IP. Approve — the tool refuses it, and the agent explains why.

> "Layer two: even when someone insists, the tool blocks IMSIs and IP addresses in code.
> Sensitive data can't land on a permanent public ledger."

### 6. Ordinary files vs the ledger — 2 min

> "Our own logs, chat history and saved reports are files on a server. An admin — or a
> compromised agent — could edit them."

**Click:** 📜 **Audit Trail** → ✋ approve. Everything from this demo, newest first, with
times and a HashScan link.

**Type:** `Verify report entry <N>` (the number from scene 4) → ✋ approve → ✅ verified.

Now play the insider, in the VM2 terminal:

```bash
cd ~/netagent
f=$(ls -t data/reports/*.md | head -1)   # newest fingerprinted report
cp "$f" /tmp/report.bak                  # keep the original
nano "$f"                                # change one word in the root cause, save
```

**Type:** `Verify report entry <N>` again → ✋ approve → ❌ **does not match**; the two
hashes differ.

> "One changed word, and the ledger catches it. Whoever edited the file can't edit the
> ledger."

Afterwards, restore it: `cp /tmp/report.bak "$f"` (verification passes again).

### Close — 15s

> "Human approval decides what the AI may do. The ledger proves what it actually did —
> cheaply, in seconds, verifiable by anyone."

---

## If something goes wrong

| Symptom | Cause / fix |
|---|---|
| Read-back says `found: false` | Mirror node hasn't indexed it yet. Ask again after a few seconds. |
| Second approval prompt never appears after the restart | Restart failed → no entry, by design. Show that as a feature: failed actions aren't recorded as done. |
| Entry never written, no prompt | Chat started before the prompt rule loaded, or `enabled: false`. Open a new chat. |
| Approval prompt vanished | 120s timeout auto-denies, and a page reload drops the pending call. Repeat the request. |
| Buttons do nothing | You're in a chat reopened from history (read-only). Open a new chat. |
| No 📜 Audit Trail button / no `hcs_*` tools listed | `enabled: false`, or the app wasn't restarted after a config change. |
| Chat start fails with `ConnectError` | VM1's MCP server unreachable — not Hedera. Check VM1, refresh. |
| `not configured` error | `HEDERA_*` variables missing from `.env`. |
| No 🔏 button under the report | The reply lacked the `**Root cause:**` heading (e.g. inconclusive RCA). Re-run, or skip the fingerprint beats. |
| Verify says the saved copy is missing | The file under `data/reports/` was deleted or renamed — it must keep its `<sha256>.md` name. |
| Scene 5 verbatim request still gets sanitized | The model is allowed to be careful. Say "layer one caught it again" and move on. |
| Entries land on the old topic after changing `topic_id` | App not restarted — the write client caches the topic. `./netagent.sh restart`. |

---

## What's behind each beat

| Beat | Mechanism |
|---|---|
| Automatic entry after a change | System-prompt audit rule + `hcs_submit_message` |
| HashScan links | `explorer_base_url` in `config/hedera.yaml` |
| 📜 Audit Trail button | `hcs_list_recent` (mirror node, newest first) |
| 🔏 Fingerprint report | `app.py` callback → `fingerprint_report()`: SHA-256 in code, copy in `data/reports/` |
| Tamper check | `hcs_verify_report`: re-hash the saved copy, compare with the ledger |
| Privacy layer one | System-prompt rule: no IMSIs, IPs or keys in entries |
| Privacy layer two | IMSI/IPv4 check inside `hcs_submit_message` |

Scene 5's behaviour was checked against the live model (3/3 runs each): the plain request
was sanitized by the agent; the verbatim request reached the tool and was refused.
