import functools
from datetime import datetime, timezone
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.tools import tool

from agent.llm import get_embeddings

_PERSIST_DIR = Path(__file__).parent.parent.parent / "data" / "memory_store"
_COLLECTION_NAME = "netagent_incidents"
_TOP_K = 3


@functools.lru_cache(maxsize=1)
def _get_store() -> Chroma:
    _PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    return Chroma(
        collection_name=_COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(_PERSIST_DIR),
    )


@tool
async def recall_similar_incidents(symptom_description: str) -> str:
    """Search past resolved incidents for ones with similar symptoms.

    Use this early in a root-cause investigation — before or alongside
    checking live health/logs/config — to check whether this failure
    pattern has been diagnosed before. If a close match is found, cite it
    explicitly in your Root Cause / Evidence report (e.g. "Per a similar
    incident on <date> affecting <NF>...").
    """
    if not _PERSIST_DIR.exists():
        return "No incident memory recorded yet."

    store = _get_store()
    results = store.similarity_search(symptom_description, k=_TOP_K)
    if not results:
        return "No similar past incidents found."

    sections = []
    for doc in results:
        meta = doc.metadata
        sections.append(
            f"[{meta.get('nf', 'unknown').upper()} — {meta.get('timestamp', 'unknown date')}]\n"
            f"{doc.page_content}"
        )
    return "\n\n---\n\n".join(sections)


@tool
async def record_incident(nf: str, symptom: str, root_cause: str, fix_action: str) -> str:
    """Record a resolved incident to memory for future recall.

    Call this after you have delivered a Root Cause / Evidence / Recommended
    Action report and are confident in the diagnosis, so a future
    investigation with similar symptoms can recall it. Do not call this for
    inconclusive or unresolved investigations.

    Args:
        nf: the network function primarily responsible (e.g. "amf", "smf", "upf").
        symptom: a short description of the observed symptom (what the user reported / what was seen).
        root_cause: the one-sentence root cause you reported.
        fix_action: the recommended or applied fix.
    """
    store = _get_store()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    content = (
        f"Symptom: {symptom}\n"
        f"Root cause: {root_cause}\n"
        f"Fix: {fix_action}"
    )
    doc = Document(
        page_content=content,
        metadata={"nf": nf.lower(), "timestamp": timestamp},
    )
    store.add_documents([doc])
    return f"Incident recorded to memory ({nf.upper()}, {timestamp})."
