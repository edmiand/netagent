import asyncio
import base64
import functools
import os
import re
import threading
from pathlib import Path

import httpx
import yaml
from langchain_core.tools import tool

_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "hedera.yaml"

# Single-chunk HCS message limit. Longer payloads would need the SDK's chunked
# submit — not supported here; audit entries should be short (or a hash).
_MAX_MESSAGE_BYTES = 1024

# Mirror node lags the consensus receipt by ~1–3s (HEDERA.md §9). Poll a little
# past that so a read straight after a submit usually succeeds in one call.
_MIRROR_POLL_SECONDS = 10
_MIRROR_POLL_INTERVAL = 0.5

# Topic messages are public and permanent. Refuse anything that looks like a
# UE identifier or an IP address rather than trusting the model to hash it.
_SENSITIVE_RE = re.compile(
    r"\bimsi-?\d+|\b\d{15}\b|\b(?:\d{1,3}\.){3}\d{1,3}\b", re.IGNORECASE
)

# The SDK is synchronous and its Client is shared; serialize submits.
_submit_lock = threading.Lock()


def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        return {}
    with _CONFIG_PATH.open() as fh:
        return yaml.safe_load(fh) or {}


def is_enabled() -> bool:
    return bool(_load_config().get("enabled", False))


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


@tool
async def hcs_submit_message(message: str) -> dict:
    """Write a short entry to NetAgent's audit trail on the Hedera Consensus
    Service (a public, permanent, tamper-evident log).

    Use this only when the user asks to record something on the ledger /
    audit trail — e.g. a one-line summary of an action taken or an incident
    resolved, or a sha256 hash of a report. The message is PUBLIC and can
    never be deleted: never include IMSIs, subscriber keys, IP addresses or
    other internal identifiers (hash them first). Max 1024 bytes.

    Returns {topic_id, status, sequence_number}; keep the sequence_number to
    read the entry back with hcs_read_message.
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

    Returns {topic_id, sequence_number, message, consensus_timestamp}, or
    {found: false} if the mirror node does not have it (yet).
    """
    if err := _not_configured():
        return err
    cfg = _load_config()
    topic_id = str(cfg["topic_id"])
    url = f"{cfg['mirror_base_url'].rstrip('/')}/api/v1/topics/{topic_id}/messages/{sequence_number}"

    loop = asyncio.get_running_loop()
    deadline = loop.time() + _MIRROR_POLL_SECONDS
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            while True:
                resp = await http.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "topic_id": topic_id,
                        "sequence_number": data["sequence_number"],
                        "message": base64.b64decode(data["message"]).decode(errors="replace"),
                        "consensus_timestamp": data["consensus_timestamp"],
                    }
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
