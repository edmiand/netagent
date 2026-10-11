import asyncio
import base64
import functools
import hashlib
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml
from langchain_core.tools import tool

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "hedera.yaml"

# Full text of fingerprinted reports, named <sha256>.md. The ledger holds only the
# hash; this copy is what hcs_verify_report re-hashes. Gitignored.
_REPORTS_DIR = Path(__file__).parent.parent.parent / "data" / "reports"

# Single-chunk HCS message limit. Longer payloads would need the SDK's chunked
# submit — not supported here; audit entries should be short (or a hash).
_MAX_MESSAGE_BYTES = 1024

# Mirror node lags the consensus receipt by ~1–3s (HEDERA.md §9). Poll a little
# past that so a read straight after a submit usually succeeds in one call.
_MIRROR_POLL_SECONDS = 10
_MIRROR_POLL_INTERVAL = 0.5

_MAX_RECENT = 25

# Topic messages are public and permanent. Refuse anything that looks like a
# UE identifier or an IP address rather than trusting the model to hash it.
_SENSITIVE_RE = re.compile(
    r"\bimsi-?\d+|\b\d{15}\b|\b(?:\d{1,3}\.){3}\d{1,3}\b", re.IGNORECASE
)

_FINGERPRINT_PREFIX = "RCA report sha256:"
_FINGERPRINT_RE = re.compile(re.escape(_FINGERPRINT_PREFIX) + r"([0-9a-f]{64})")

# The SDK is synchronous and its Client is shared; serialize submits.
_submit_lock = threading.Lock()


def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    with _CONFIG_PATH.open() as fh:
        return yaml.safe_load(fh) or {}


def is_enabled() -> bool:
    return bool(_load_config().get("enabled", False))


def _explorer_url(topic_id: str) -> str | None:
    base = _load_config().get("explorer_base_url")
    return f"{base.rstrip('/')}/topic/{topic_id}" if base else None


def _iso(consensus_timestamp: str) -> str:
    """Mirror timestamps are '<seconds>.<nanos>' strings; render as UTC ISO."""
    secs = float(consensus_timestamp)
    return datetime.fromtimestamp(secs, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


@functools.lru_cache(maxsize=1)
def _get_client():
    """Return (client, operator_key, topic_id), or None if credentials are missing."""
    from hiero_sdk_python import AccountId, Client, Network, PrivateKey, TopicId

    op_id = os.environ.get("HEDERA_OPERATOR_ID")
    op_key = os.environ.get("HEDERA_OPERATOR_KEY")
    if not op_id or not op_key:
        return None

    cfg = _load_config()
    # DER-encoded key carries its type; a raw 0x hex key would be guessed as
    # Ed25519 and break ECDSA accounts (HEDERA.md §3).
    key = PrivateKey.from_string(op_key)
    client = Client(Network(cfg.get("network", "testnet")))
    client.set_operator(AccountId.from_string(op_id), key)
    return client, key, TopicId.from_string(str(cfg["topic_id"]))


def _submit_blocking(message: str) -> dict:
    from hiero_sdk_python import ResponseCode, TopicMessageSubmitTransaction

    client, key, topic_id = _get_client()
    with _submit_lock:
        receipt = (
            TopicMessageSubmitTransaction(topic_id=topic_id, message=message)
            .freeze_with(client)
            .sign(key)
            .execute(client)
        )
    status = ResponseCode(receipt.status).name
    result = {"topic_id": str(topic_id), "status": status}
    if receipt.status == ResponseCode.SUCCESS:
        result["sequence_number"] = receipt.topic_sequence_number
    if url := _explorer_url(str(topic_id)):
        result["explorer_url"] = url
    return result


def _not_configured() -> dict | None:
    if not _load_config().get("topic_id"):
        return {"error": "No topic_id set in config/hedera.yaml."}
    if not (os.environ.get("HEDERA_OPERATOR_ID") and os.environ.get("HEDERA_OPERATOR_KEY")):
        return {
            "error": "The Hedera tools are not configured — HEDERA_OPERATOR_ID / "
                     "HEDERA_OPERATOR_KEY are missing from .env."
        }
    return None


def _mirror_base() -> tuple[str, str]:
    cfg = _load_config()
    return cfg["mirror_base_url"].rstrip("/"), str(cfg["topic_id"])


def _entry(data: dict) -> dict:
    return {
        "sequence_number": data["sequence_number"],
        "message": base64.b64decode(data["message"]).decode(errors="replace"),
        "consensus_timestamp": data["consensus_timestamp"],
        "time": _iso(data["consensus_timestamp"]),
    }


async def _fetch_message(sequence_number: int) -> dict:
    """GET one topic message, polling through the mirror node's indexing lag."""
    base, topic_id = _mirror_base()
    url = f"{base}/api/v1/topics/{topic_id}/messages/{sequence_number}"
    explorer = _explorer_url(topic_id)

    loop = asyncio.get_running_loop()
    deadline = loop.time() + _MIRROR_POLL_SECONDS
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            while True:
                resp = await http.get(url)
                if resp.status_code == 200:
                    result = {"topic_id": topic_id, **_entry(resp.json())}
                    if explorer:
                        result["explorer_url"] = explorer
                    return result
                if resp.status_code != 404 or loop.time() >= deadline:
                    break
                await asyncio.sleep(_MIRROR_POLL_INTERVAL)
    except Exception as exc:
        return {"error": f"Mirror node read failed: {type(exc).__name__}: {exc}"}

    if resp.status_code == 404:
        return {"found": False, "topic_id": topic_id, "sequence_number": sequence_number,
                "note": f"Not on the mirror node after {_MIRROR_POLL_SECONDS}s — the "
                        "sequence number may not exist yet."}
    return {"error": f"Mirror node returned HTTP {resp.status_code}: {resp.text[:200]}"}


@tool
async def hcs_submit_message(message: str) -> dict:
    """Write a short entry to NetAgent's audit trail on the Hedera Consensus
    Service (a public, permanent, tamper-evident log).

    Use this when the user asks to record something on the ledger / audit
    trail, or when your rules call for an audit entry — a one-line summary of
    an action taken or an incident resolved. The message is PUBLIC and can
    never be deleted: never include IMSIs, subscriber keys, IP addresses or
    other internal identifiers (hash them first). Max 1024 bytes.

    Returns {topic_id, status, sequence_number, explorer_url}; keep the
    sequence_number to read the entry back with hcs_read_message, and give
    the user explorer_url as a link so they can check it independently.
    """
    if err := _not_configured():
        return err
    if len(message.encode()) > _MAX_MESSAGE_BYTES:
        return {"error": f"Message is {len(message.encode())} bytes; the limit is "
                         f"{_MAX_MESSAGE_BYTES}. Shorten it or submit a hash instead."}
    if _SENSITIVE_RE.search(message):
        return {"error": "Message looks like it contains an IMSI or IP address. HCS "
                         "messages are public and permanent — remove or hash it first."}
    try:
        return await asyncio.to_thread(_submit_blocking, message)
    except Exception as exc:
        return {"error": f"HCS submit failed: {type(exc).__name__}: {exc}"}


@tool
async def hcs_read_message(sequence_number: int) -> dict:
    """Read one entry back from NetAgent's Hedera audit-trail topic by its
    sequence number (as returned by hcs_submit_message), via the public
    mirror node. Use it to confirm an entry was recorded or to show what an
    earlier entry said.

    Returns {topic_id, sequence_number, message, time, consensus_timestamp,
    explorer_url}, or {found: false} if the mirror node does not have it (yet).
    """
    if err := _not_configured():
        return err
    return await _fetch_message(sequence_number)


@tool
async def hcs_list_recent(limit: int = 10) -> dict:
    """List the most recent entries on NetAgent's Hedera audit-trail topic,
    newest first, via the public mirror node. Use this when the user asks to
    see the audit trail / ledger / recent recorded actions.

    Present the entries as a markdown table (# · time · entry) and give the
    user explorer_url as a link so they can verify them independently.
    limit: 1–25 (default 10).
    """
    if err := _not_configured():
        return err
    limit = max(1, min(int(limit), _MAX_RECENT))
    base, topic_id = _mirror_base()
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(f"{base}/api/v1/topics/{topic_id}/messages",
                                  params={"order": "desc", "limit": limit})
        resp.raise_for_status()
    except Exception as exc:
        return {"error": f"Mirror node read failed: {type(exc).__name__}: {exc}"}

    result = {"topic_id": topic_id,
              "entries": [_entry(m) for m in resp.json().get("messages", [])]}
    if explorer := _explorer_url(topic_id):
        result["explorer_url"] = explorer
    return result


async def fingerprint_report(report: str) -> dict:
    """Save a report locally and record its sha256 on the ledger.

    Called from the UI's "Fingerprint report" button (the click is the user's
    approval), not exposed to the model — a model can't compute a hash, and
    re-typing the report would change it.
    """
    if err := _not_configured():
        return err
    digest = hashlib.sha256(report.encode()).hexdigest()
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _REPORTS_DIR / f"{digest}.md"
    path.write_bytes(report.encode())  # exact bytes that were hashed
    try:
        result = await asyncio.to_thread(_submit_blocking, f"{_FINGERPRINT_PREFIX}{digest}")
    except Exception as exc:
        return {"error": f"HCS submit failed: {type(exc).__name__}: {exc}"}
    return {**result, "sha256": digest, "report_path": str(path)}


@tool
async def hcs_verify_report(sequence_number: int) -> dict:
    """Check that a fingerprinted report has not been altered since it was
    recorded. Reads the audit-trail entry with this sequence number (it must be
    an "RCA report sha256:…" entry), re-hashes the locally saved copy of that
    report, and compares the two.

    Returns {verified: true/false, recorded_sha256, current_sha256, time,
    explorer_url}. verified=false means the saved report was modified after it
    was recorded — say so plainly.
    """
    if err := _not_configured():
        return err
    entry = await _fetch_message(sequence_number)
    if "message" not in entry:
        return entry
    match = _FINGERPRINT_RE.search(entry["message"])
    if not match:
        return {"error": f"Entry {sequence_number} is not a report fingerprint "
                         f"(it says: {entry['message'][:120]!r})."}
    recorded = match.group(1)
    path = _REPORTS_DIR / f"{recorded}.md"
    if not path.exists():
        return {"verified": False, "recorded_sha256": recorded,
                "error": "The saved copy of this report is missing — it was deleted or moved."}
    current = hashlib.sha256(path.read_bytes()).hexdigest()
    result = {
        "verified": current == recorded,
        "sequence_number": sequence_number,
        "recorded_sha256": recorded,
        "current_sha256": current,
        "recorded_at": entry["time"],
        "report_path": str(path),
    }
    if "explorer_url" in entry:
        result["explorer_url"] = entry["explorer_url"]
    return result
