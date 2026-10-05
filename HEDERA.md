# Hedera Consensus Service (HCS) — integration notes

Goal: let NetAgent write to and read from a Hedera testnet topic (e.g. an
immutable audit trail of agent actions, or hashes of incident reports).

Legend: **[V]** verified by running it · **[D]** taken from docs/source, not run · **[U]** unverified assumption

## 1. Status

- SDK install on this ARM64 VM: **[V]**
- Live testnet write (create topic, submit message): **[U]** — blocked, no
  `HEDERA_OPERATOR_ID` / `HEDERA_OPERATOR_KEY` in `.env` yet
- Mirror node read-back: **[U]**
- Submit-to-readable latency: **[U]** — no measurements yet
- Topic ID: **[U]** — none created

## 2. SDK

| Item | Value | Mark |
|---|---|---|
| PyPI package | `hiero-sdk-python` | [V] installed from PyPI |
| Import name | `hiero_sdk_python` | [V] |
| Latest version seen | `0.2.10` (released 2026-07-30) | [V] (pip resolved it) / [D] release date from PyPI page |
| Source | https://github.com/hiero-ledger/hiero-sdk-python (Apache-2.0, official Hiero org) | [D] |
| Python | `>=3.10,<4` (tested 3.10–3.14). Repo needs 3.11+, so compatible | [D] + [V] on 3.12.3 |
| Wheel | `py3-none-any` for the SDK itself | [D] PyPI page; [V] wheel name in pip output |
| Maturity | PyPI classifier "Pre-Alpha" | [D] |
| Platform | Native aarch64 wheels resolved for `grpcio 1.84.0`, `cryptography 49.0.0`, `protobuf 7.36.2`, `pycryptodome 3.23.0`, `pydantic-core 2.46.5` on this VM — no compile step needed | [V] |

Install (throwaway venv, outside repo):

```bash
python3.12 -m venv <scratch>/hedera_venv
<scratch>/hedera_venv/bin/pip install hiero-sdk-python python-dotenv httpx
```

For the repo itself, add `hiero-sdk-python` to `pyproject.toml` and run
`.venv/bin/pip install -e .`. Do not hand-pin transitive versions; let pip resolve.
Dependency conflicts with the repo's existing stack (langchain, chromadb, chainlit)
are **[U]** — check with `pip install -e .` in the real `.venv` before relying on it.

## 3. Credentials

**[D]** from Hedera Portal (https://portal.hedera.com/): a free account auto-provisions
a testnet account with an Account ID (`0.0.x`), a DER-encoded private key (`302e…`),
and testnet HBAR from the faucet on the dashboard. Not re-checked against the live portal.

Add to `/home/dmandrey/netagent/.env` (gitignored, never commit):

```
HEDERA_OPERATOR_ID=0.0.xxxxxxx
HEDERA_OPERATOR_KEY=302e...
```

**Gotcha [V]:** the SDK's `Client.from_env()` reads `OPERATOR_ID` / `OPERATOR_KEY`
(no `HEDERA_` prefix) and also calls `load_dotenv()` itself. It will **not** find the
`HEDERA_*` names. Do not use `from_env()`. Read the `HEDERA_*` values explicitly and call
`set_operator()` (see §4). Consider adding `HEDERA_` names to `.env.example` only.

## 4. Exact calls (from `examples/consensus/` in the SDK repo, read [D]; not yet executed live)

```python
from hiero_sdk_python import (
    AccountId, Client, Network, PrivateKey, ResponseCode,
    TopicCreateTransaction, TopicMessageSubmitTransaction,
)

client = Client(Network("testnet"))
client.set_operator(AccountId.from_string(op_id), PrivateKey.from_string(op_key))

# Create topic
tx = TopicCreateTransaction(memo="netagent", admin_key=op_key.public_key()) \
        .freeze_with(client).sign(op_key)
receipt = tx.execute(client)            # blocking
assert receipt.status == ResponseCode.SUCCESS
topic_id = receipt.topic_id

# Submit message
tx = TopicMessageSubmitTransaction(topic_id=topic_id, message="sha256:…") \
        .freeze_with(client).sign(op_key)
receipt = tx.execute(client)
seq = receipt.topic_sequence_number     # [D] attribute name — verify on first run
```

Notes:
- `admin_key` in `TopicCreateTransaction` is what the examples pass. Without it the topic
  is immutable and cannot be deleted. Keep it set. **[D]**
- `freeze_with(client)` + `sign(key)` + `execute(client)` is the pattern in every example. **[D]**
- `receipt.topic_sequence_number` is used by the test script but **[U]** until run.
- Message size: `TopicMessageSubmitTransaction` has a per-message limit (~1 KB on Hedera
  proper); larger payloads need `topic_message_submit_chunked_transaction.py` (present in the SDK). **[D]**

## 5. Mirror node read-back (REST, no SDK needed)

Public testnet mirror: `https://testnet.mirrornode.hedera.com` **[D]**

- One message by sequence: `GET /api/v1/topics/{topic_id}/messages/{seq}`
- Latest messages: `GET /api/v1/topics/{topic_id}/messages?order=desc&limit=N`

The `message` field in the response is **base64**-encoded. Decode before comparing. **[D]**
The mirror node lags consensus by a short, variable delay, which is what the latency test measures. **[U]**

Config rule (CLAUDE.md): read the mirror URL from a config file, not hardcoded in code.

## 6. Async / event-loop behavior

**[V]** The SDK is fully synchronous:
- `grep` for `async def`, `grpc.aio`, `asyncio` in the installed package → zero hits.
- `execute()` performs blocking gRPC calls.

Consequence for Chainlit (asyncio event loop, `app.py`):
- Calling `tx.execute(client)` directly inside an `async` handler **blocks the whole
  Chainlit server** for the consensus round-trip (seconds, not milliseconds). **Do not do this.**
- Wrap calls in `await asyncio.to_thread(...)` (or `loop.run_in_executor`). **[U]** until tested.
- Reuse one `Client` per process. Creating a client per call re-opens gRPC channels. **[D]**
- Mirror REST reads: use `httpx.AsyncClient` (already a repo dependency). No thread needed. **[D]**

## 7. Feature integration plan (checklist, not done)

Follows the existing local-tool pattern (`agent/tools/rag.py`, `agent/tools/release_check.py`):

1. `pyproject.toml` — add `hiero-sdk-python`. Run `.venv/bin/pip install -e .`.
2. `config/hedera.yaml` (new) — `network: testnet`, `mirror_base_url`, `topic_id` (or
   empty = create on first use), `enabled: false` default. No URLs in Python code.
3. `.env.example` — document `HEDERA_OPERATOR_ID`, `HEDERA_OPERATOR_KEY`. Real values stay in `.env`.
4. `agent/tools/hedera.py` (new) — two local tools:
   - `hcs_submit_message(message: str)` — thread-wrapped submit, returns
     `{topic_id, sequence_number, status}` (MCP-style structured dict, per CLAUDE.md).
   - `hcs_read_message(sequence_number: int)` — async httpx mirror GET, returns decoded JSON.
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
- **[U]** Testnet operator account funding: how many messages/topics the faucet HBAR covers.
- **[U]** Real submit-to-readable latency (planned: 5-message test in `scratch/hedera_explore/test_hcs.py`).
- **[U]** Whether the SDK's `TopicMessageSubmitTransaction` raises or returns non-SUCCESS
  receipts on network errors — needs a failure-path test.
- **[D]** Pre-Alpha classification: pin the exact version in `pyproject.toml` when added, and
  expect API churn between minor versions.
- Data policy: anything written to a public testnet topic is public and permanent. Do not
  send UE identifiers, subscriber keys, or internal IPs. Hash them first if needed.

## 9. Verification log

| Step | Result | Mark |
|---|---|---|
| `pip install hiero-sdk-python` in Python 3.12.3 venv, aarch64 | Succeeded, all wheels resolved | [V] |
| `grep async` in installed SDK | 0 hits; `execute()` is blocking | [V] |
| `Client.from_env()` env var names | Reads `OPERATOR_ID`/`OPERATOR_KEY` | [V] (source read) |
| Live topic create on testnet | Not run | [U] |
| Live message submit + mirror read | Not run | [U] |
| 5-message latency | Not run | [U] |
