# Hedera Consensus Service (HCS) — integration notes

Goal: let NetAgent write to and read from a Hedera testnet topic (e.g. an
immutable audit trail of agent actions, or hashes of incident reports).

Legend: **[V]** verified by running it · **[D]** taken from docs/source, not run · **[U]** unverified assumption

## 1. Status

- SDK install on this ARM64 VM: **[V]** (throwaway venv; not yet in the repo's `.venv`)
- Credentials in `.env`: **[V]** — `HEDERA_OPERATOR_ID` / `HEDERA_OPERATOR_KEY` set (ED25519, DER)
- Live testnet write (create topic, submit message): **[V]** (2026-10-11)
- Mirror node read-back: **[V]** — all messages decoded and matched
- Submit-to-readable latency: **[V]** — ~2.5s average, see §9
- Topic ID: **[V]** `0.0.10994808` (testnet, admin key = current ED25519 operator key) —
  https://hashscan.io/testnet/topic/0.0.10994808

## 2. SDK

| Item | Value | Mark |
|---|---|---|
| PyPI package | `hiero-sdk-python` | [V] installed from PyPI |
| Import name | `hiero_sdk_python` | [V] |
| Version used in live tests | `0.3.0` (pip resolved it on 2026-10-11; an earlier install got `0.2.10`) | [V] |
| Source | https://github.com/hiero-ledger/hiero-sdk-python (Apache-2.0, official Hiero org) | [D] |
| Python | `>=3.10,<4` (tested 3.10–3.14). Repo needs 3.11+, so compatible | [D] + [V] on 3.12.3 |
| Wheel | `py3-none-any` for the SDK itself | [D] PyPI page; [V] wheel name in pip output |
| Maturity | PyPI classifier "Pre-Alpha" | [D] |
| Platform | Native aarch64 wheels resolved for `grpcio 1.84.0`, `cryptography 49.0.0`, `protobuf 7.36.2`, `pycryptodome 3.23.0`, `pydantic-core 2.46.5` on this VM — no compile step needed | [V] |

Install (throwaway venv, outside repo):

```bash
python3 -m venv <scratch>/hedera_venv
<scratch>/hedera_venv/bin/pip install hiero-sdk-python python-dotenv httpx
```

For the repo itself, add `hiero-sdk-python` to `pyproject.toml` and run
`.venv/bin/pip install -e .`. Do not hand-pin transitive versions; let pip resolve.
Dependency conflicts with the repo's existing stack (langchain, chromadb, chainlit)
are **[U]** — check with `pip install -e .` in the real `.venv` before relying on it.

## 3. Credentials

From Hedera Portal (https://portal.hedera.com/), Testnet: the dashboard shows the
Account ID (`0.0.x`), the private key in DER and HEX form, and 1000 testnet HBAR.
The portal lets you create either an ECDSA or an ED25519 account. **[V]**

Add to `/home/dmandrey/netagent/.env` (gitignored, never commit):

```
HEDERA_OPERATOR_ID=0.0.xxxxxxx
HEDERA_OPERATOR_KEY=302e...        # the DER-encoded private key
```

**Use the DER-encoded private key. [V]** DER carries the key type, so plain
`PrivateKey.from_string()` loads it correctly:
- ED25519 DER starts `302e…`; ECDSA (secp256k1) DER starts `3030…`.
- The raw HEX form (`0x` + 64 hex chars) does not say which type it is. `from_string()`
  then guesses **Ed25519** (and warns). For an ECDSA account that guess produces the
  wrong public key and transactions would fail signature checks. If you only have the
  HEX form of an ECDSA key, load it with `PrivateKey.from_string_ecdsa()`.
- Sanity check: compare `op_key.public_key().to_string()` with the `key` field from
  `GET <mirror>/api/v1/accounts/<account_id>` — it also reports `_type`
  (`ED25519` / `ECDSA_SECP256K1`).

Current `.env` holds an ED25519 account with a DER key. **[V]**

**Gotcha [V]:** the SDK's `Client.from_env()` reads `OPERATOR_ID` / `OPERATOR_KEY`
(no `HEDERA_` prefix) and also calls `load_dotenv()` itself. It will **not** find the
`HEDERA_*` names. Do not use `from_env()`. Read the `HEDERA_*` values explicitly and call
`set_operator()` (see §4). Consider adding `HEDERA_` names to `.env.example` only.

Never paste a private key into chat, tickets or docs — the account ID and public key are
enough to verify a setup. (The testnet key now in `.env` was pasted into a chat once;
fine for testnet, rotate it before anything that matters.)

## 4. Exact calls (run live against testnet with SDK 0.3.0) **[V]**

```python
import os
from hiero_sdk_python import (
    AccountId, Client, Network, PrivateKey, ResponseCode,
    TopicCreateTransaction, TopicMessageSubmitTransaction,
)

op_id = AccountId.from_string(os.environ["HEDERA_OPERATOR_ID"])
op_key = PrivateKey.from_string(os.environ["HEDERA_OPERATOR_KEY"])   # DER, see §3

client = Client(Network("testnet"))
client.set_operator(op_id, op_key)

# Create topic
receipt = (TopicCreateTransaction(memo="netagent", admin_key=op_key.public_key())
           .freeze_with(client).sign(op_key).execute(client))   # blocking
assert receipt.status == ResponseCode.SUCCESS
topic_id = receipt.topic_id

# Submit message
receipt = (TopicMessageSubmitTransaction(topic_id=topic_id, message="sha256:…")
           .freeze_with(client).sign(op_key).execute(client))
seq = receipt.topic_sequence_number
```

Notes:
- `receipt.topic_id` and `receipt.topic_sequence_number` work as named. **[V]**
- `ResponseCode(receipt.status).name` gives a readable status (`"SUCCESS"`). **[V]**
- `admin_key` in `TopicCreateTransaction` is what the examples pass. Without it the topic
  is immutable and cannot be deleted. Keep it set. **[D]**
- No `submit_key` is set, so anyone can post to the topic; only the admin key can update or
  delete it. Set a `submit_key` if only NetAgent should write. **[D]**
- Message size: `TopicMessageSubmitTransaction` has a per-message limit (~1 KB on Hedera
  proper); larger payloads need `topic_message_submit_chunked_transaction.py` (present in the SDK). **[D]**

## 5. Mirror node read-back (REST, no SDK needed) **[V]**

Public testnet mirror: `https://testnet.mirrornode.hedera.com`

- One message by sequence: `GET /api/v1/topics/{topic_id}/messages/{seq}` — returns 404
  until the mirror has the message, then 200. **[V]**
- Latest messages: `GET /api/v1/topics/{topic_id}/messages?order=desc&limit=N` **[D]**
- Account info (balance, key type): `GET /api/v1/accounts/{account_id}` **[V]**

The `message` field in the response is **base64**-encoded. Decode before comparing. **[V]**
The mirror lags the receipt by ~1–3s (see §9), so a write followed by a read must poll
(the test polled every 0.25s, 60s timeout). **[V]**

Config rule (CLAUDE.md): read the mirror URL from a config file, not hardcoded in code.

## 6. Async / event-loop behavior

**[V]** The SDK is fully synchronous:
- `grep` for `async def`, `grpc.aio`, `asyncio` in the installed package → zero hits.
- `execute()` performs blocking gRPC calls — measured ~0.6s for a submit, ~0.9s for a
  topic create. **[V]**

Consequence for Chainlit (asyncio event loop, `app.py`):
- Calling `tx.execute(client)` directly inside an `async` handler **blocks the whole
  Chainlit server** for that time. **Do not do this.**
- Wrap calls in `await asyncio.to_thread(...)` (or `loop.run_in_executor`). **[U]** until tested
  inside Chainlit.
- Reuse one `Client` per process. Creating a client per call re-opens gRPC channels. **[D]**
- Mirror REST reads: use `httpx.AsyncClient` (already a repo dependency). No thread needed. **[D]**

## 7. Feature integration plan (checklist, not done)

Follows the existing local-tool pattern (`agent/tools/rag.py`, `agent/tools/release_check.py`):

1. `pyproject.toml` — add `hiero-sdk-python` (pin the exact version, see §8). Run `.venv/bin/pip install -e .`.
2. `config/hedera.yaml` (new) — `network: testnet`, `mirror_base_url`, `topic_id: 0.0.10994808`
   (or empty = create on first use), `enabled: false` default. No URLs in Python code.
3. `.env.example` — document `HEDERA_OPERATOR_ID`, `HEDERA_OPERATOR_KEY` (DER). Real values stay in `.env`.
4. `agent/tools/hedera.py` (new) — two local tools:
   - `hcs_submit_message(message: str)` — thread-wrapped submit, returns
     `{topic_id, sequence_number, status}` (MCP-style structured dict, per CLAUDE.md).
   - `hcs_read_message(sequence_number: int)` — async httpx mirror GET, returns decoded JSON.
     Must handle 404 "not on the mirror yet" (expected for ~1–3s after submit).
   Keep the tool surface narrow (no free-form topic ID from the model unless intended).
5. `app.py` `_build_tools()` — append the new tools only when `hedera.yaml` `enabled: true`
   and credentials are present. Degrade with a clear message if not (same as TAVILY_API_KEY).
6. Approval: these are write actions. They go through Human Approval Mode automatically
   via the existing wrapper in `agent/approval.py`. Verify this in the UI. **[U]**
7. `prompts/system.txt` — only if the agent needs a rule about when to write to HCS.
   Tool schemas come from the tool definitions, not the prompt (CLAUDE.md).
8. `test_integration.py` — optional fourth check (HCS round-trip), skipped if unconfigured.
9. Chainlit UI — tool calls already stream as Steps; no UI work needed.

## 8. Open questions / risks

- **[U]** Does the SDK's protobuf/grpcio pin collide with anything in the repo's `.venv`?
- **[V]** Cost: topic create + 5 submits ≈ 0.22 testnet HBAR, so the 1000 HBAR from the
  portal covers thousands of messages.
- **[U]** Whether the SDK's `TopicMessageSubmitTransaction` raises or returns non-SUCCESS
  receipts on network errors — needs a failure-path test.
- **[V]** API churn is real: pip resolved `0.2.10` on 2026-10-05 and `0.3.0` on 2026-10-11.
  Pre-Alpha classification — pin the exact version in `pyproject.toml` when added.
- Receipt time was a flat ~0.63s on every submit, which looks like the SDK's receipt-poll
  interval rather than true consensus time. Not a problem, just don't read it as network latency.
- Data policy: anything written to a public testnet topic is public and permanent. Do not
  send UE identifiers, subscriber keys, or internal IPs. Hash them first if needed.
- Leftover topic `0.0.10994728` (created in the first live test with an earlier ECDSA
  account, admin key = that ECDSA key). Unused; ignore it.

## 9. Verification log

| Step | Result | Mark |
|---|---|---|
| `pip install hiero-sdk-python` in Python 3.12.3 venv, aarch64 | Succeeded, all wheels resolved | [V] |
| `grep async` in installed SDK | 0 hits; `execute()` is blocking | [V] |
| `Client.from_env()` env var names | Reads `OPERATOR_ID`/`OPERATOR_KEY` | [V] (source read) |
| Key parsing (2026-10-11) | HEX ECDSA key via `from_string()` → wrong (Ed25519) public key; `from_string_ecdsa()` → matches mirror. ED25519 DER via `from_string()` → matches mirror | [V] |
| Live topic create, ECDSA account (2026-10-11) | SUCCESS, `0.0.10994728`, 0.86s | [V] |
| 5-message submit + mirror read, ECDSA account | All SUCCESS, all matched; receipt 0.63s; mirror 1.86–3.56s (avg 2.31s); cost 0.22 HBAR | [V] |
| Live topic create, ED25519 account (2026-10-11) | SUCCESS, `0.0.10994808`, 0.88s | [V] |
| 5-message submit + mirror read, ED25519 account | All SUCCESS, all matched; receipt 0.62–0.63s; mirror 1.62–3.82s (avg 2.58s); cost 0.22 HBAR | [V] |
| `asyncio.to_thread` wrapping inside Chainlit | Not run | [U] |
| Network-error failure path | Not run | [U] |

The live tests used an ad-hoc script (create topic → 5 submits → poll mirror per message
→ compare decoded text → report latency and balance delta); it lived in a session scratch
directory and is not in the repo.
