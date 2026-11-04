# NetAgent — Hedera audit trail

> Project knowledge file 3 of 7 · snapshot as of 2026-11-04 (commit 9d501a7).
> Marks: **[V]** verified by running it · **[D]** from docs/source, not run · **[U]** unverified.

## Purpose

Every change NetAgent's AI makes to the live 5G core leaves a record on the **Hedera Consensus
Service (HCS)**, a public ledger NetAgent itself cannot edit and anyone can check on HashScan.
Human Approval Mode controls *what* the agent may do; the ledger proves *what it did* and when
(consensus timestamp, sequence order).

## Status

- Implemented in `agent/tools/hedera.py`; on in the repo (`config/hedera.yaml` `enabled: true`);
  verified end to end in the UI, including Human Approval Mode. **[V]**
- Network: Hedera **testnet**. Current topic `0.0.11309159` (created 2026-11-04; admin key and
  **submit key** = the operator's ED25519 key, so only NetAgent can write) —
  https://hashscan.io/testnet/topic/0.0.11309159. Previous topic `0.0.10994808` (no submit key,
  entries 1–16) is no longer written to.
- Not yet tested: the network-error failure path (whether the SDK raises or returns a non-SUCCESS
  receipt). **[U]**

## The four tools

| Tool | Kind | Behaviour |
|---|---|---|
| `hcs_submit_message(message)` | write | Submits to the fixed topic (the model never picks a topic). Refuses text that looks like an IMSI or IPv4 and anything over 1024 bytes. Returns `{topic_id, sequence_number, status}` |
| `hcs_read_message(sequence_number)` | read | Mirror-node read; polls up to 10 s (the mirror lags ~1–3 s) |
| `hcs_list_recent(limit)` | read | Newest N entries (max 25) with UTC times |
| `hcs_verify_report(sequence_number)` | read | Re-hashes a saved fingerprinted report and compares it with the ledger entry |

Results carry `explorer_url` (HashScan topic page) when `explorer_base_url` is configured. Without
`HEDERA_*` credentials the tools still appear but return a clear "not configured" error. With
Human Approval Mode on, every audit write costs one more approval click.

**When the agent writes** (system prompt): after each successful change (NF lifecycle,
subscriber create/update/delete, UE notification), one summary per batch, one per confident RCA,
and whenever asked. Never for reads, health checks, denied or failed actions. One line:
`<action> — <target> — <outcome>`, e.g. `NF restart — SMF — running again`.

## Report fingerprinting

RCA replies get a 🔏 **Fingerprint report** button. The app's callback — code, not the model,
which can't compute SHA-256 and would change bytes by re-typing — hashes the exact displayed text,
saves it to `data/reports/<sha256>.md` (gitignored) and submits `RCA report sha256:<hex>`. The
click is the approval, so it bypasses the Human Approval wrapper. `hcs_verify_report(seq)` later
re-hashes that file: editing or deleting it fails verification.

Caveat: the app rewrites LaTeX and removes Mermaid blocks before hashing, so the ledger hash
covers the displayed text, which won't always match the raw model output.

## Privacy

Everything on the topic is **public and permanent**. Two layers keep personal data out:
1. The system prompt tells the agent to write "a subscriber", never IMSIs, phone numbers, IPs or
   keys.
2. `hcs_submit_message` refuses IMSI- and IPv4-looking text in code, even when the user insists.
   Checked against the live model 3/3 runs each: a plain request was sanitized by the agent; a
   "verbatim" request reached the tool and was refused. **[V]**

Full reports stay private on VM2; only their fingerprint goes on the ledger.

## SDK facts and gotchas

- Package `hiero-sdk-python` (import `hiero_sdk_python`), official Hiero org, Apache-2.0,
  **Pre-Alpha** — pinned exactly; pip resolved 0.2.10 and then 0.3.0 a week apart. Native aarch64
  wheels, no compile step. **[V]**
- **Use the DER-encoded private key.** DER carries the key type (ED25519 starts `302e…`, ECDSA
  `3030…`). Raw HEX makes `PrivateKey.from_string()` guess Ed25519 — wrong for ECDSA keys (use
  `from_string_ecdsa()`). Sanity check: compare the derived public key with the mirror node's
  `GET /api/v1/accounts/<id>` `key` field. **[V]**
- `Client.from_env()` reads `OPERATOR_ID` / `OPERATOR_KEY` (no `HEDERA_` prefix) — don't use it;
  read the `HEDERA_*` values and call `set_operator()`. **[V]**
- **The SDK is fully synchronous** (blocking gRPC). Calling `execute()` inside an async Chainlit
  handler blocks the whole server, so submits run in `asyncio.to_thread`. Measured: max 79 ms
  stall on a 50 ms ticker. Reuse one client per process. **[V]**
- Mirror REST reads use `httpx.AsyncClient`; the `message` field is base64. A message is 404 on the
  mirror until indexed (~1–3 s). **[V]**
- `admin_key` on topic create keeps the topic deletable; `submit_key` restricts writers. **[V]**
- Messages over ~1 KB need the chunked submit transaction (not used — 1024-byte cap instead). **[D]**

Core calls (SDK 0.3.0, run live):

```python
client = Client(Network("testnet"))
client.set_operator(AccountId.from_string(op_id), PrivateKey.from_string(der_key))
receipt = (TopicMessageSubmitTransaction(topic_id=topic_id, message="sha256:…")
           .freeze_with(client).sign(op_key).execute(client))     # blocking
seq = receipt.topic_sequence_number
```

## Measured performance and cost **[V]**

| Metric | Value |
|---|---|
| Submit receipt | ~0.6 s (flat — likely the SDK's receipt-poll interval, not consensus time) |
| Topic create | ~0.9 s |
| Submit → readable on mirror | 1.6–3.8 s, ~2.5 s average |
| Cost | topic create + 5 submits ≈ 0.22 testnet HBAR (the portal's 1000 HBAR covers thousands) |

Verification log highlights: guards rejected IPv4 / IMSI / 1100-byte messages; read-back matched;
unknown sequence → `found: false` after 10 s; one-character edit of a fingerprinted report → ❌
with differing hash; deleted copy → clear error; the model picked the right tool for "show recent
entries" / "verify report entry 9".

## Credentials setup

Hedera Portal (portal.hedera.com) → Testnet account (ED25519 or ECDSA) → put the Account ID and the
**DER** private key in `.env` as `HEDERA_OPERATOR_ID` / `HEDERA_OPERATOR_KEY`. Never paste a
private key into chats or docs; the account ID and public key are enough to verify a setup.
