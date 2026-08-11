"""Seed the incident-memory Chroma store with a few plausible past incidents.

Optional — lets a fresh demo show a recall hit on the very first run with
Memory & Learning ON, instead of requiring the same failure to occur twice
in the same session. Rerun to add more seed incidents (existing ones are
untouched; Chroma assigns new IDs each run, so re-running duplicates rather
than overwrites — safe to run once).
"""

from datetime import datetime, timezone
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document

from agent.llm import get_embeddings

_ROOT = Path(__file__).parent.parent
_PERSIST_DIR = _ROOT / "data" / "memory_store"
_COLLECTION_NAME = "netagent_incidents"

_SEED_INCIDENTS = [
    {
        "nf": "smf",
        "timestamp": "2026-07-14",
        "symptom": "Subscriber registers successfully but PDU session establishment fails; UE never gets an IP.",
        "root_cause": "Subscriber's slice S-NSSAI (SST/SD) did not match any DNN configured on SMF, so SMF rejected session establishment.",
        "fix": "Updated the subscriber's slice assignment via the subscriber slice update tool to match a DNN SMF actually serves.",
    },
    {
        "nf": "amf",
        "timestamp": "2026-06-02",
        "symptom": "Subscriber never appears in active sessions at all; registration silently fails.",
        "root_cause": "Subscriber profile had status=1 (barred), so AMF rejected the registration request before authentication.",
        "fix": "Updated the subscriber profile to set status=0 (allowed).",
    },
    {
        "nf": "upf",
        "timestamp": "2026-05-20",
        "symptom": "UE registers and gets a PDU session, but has no actual data connectivity.",
        "root_cause": "UPF's TUN device was down after a host network restart, so user-plane traffic had no path out.",
        "fix": "Restarted the UPF NF to recreate the TUN device.",
    },
]


def main() -> None:
    documents = [
        Document(
            page_content=(
                f"Symptom: {inc['symptom']}\n"
                f"Root cause: {inc['root_cause']}\n"
                f"Fix: {inc['fix']}"
            ),
            metadata={"nf": inc["nf"], "timestamp": inc["timestamp"]},
        )
        for inc in _SEED_INCIDENTS
    ]

    _PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    Chroma.from_documents(
        documents=documents,
        embedding=get_embeddings(),
        collection_name=_COLLECTION_NAME,
        persist_directory=str(_PERSIST_DIR),
    )
    print(f"Seeded {len(documents)} incidents into {_PERSIST_DIR}")
    print(f"(Note: {datetime.now(timezone.utc).strftime('%Y-%m-%d')} is today — seed dates are in the past for demo realism.)")


if __name__ == "__main__":
    main()
