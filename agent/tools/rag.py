import functools
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.tools import tool

from agent.llm import get_embeddings

_PERSIST_DIR = Path(__file__).parent.parent.parent / "data" / "chroma"
_COLLECTION_NAME = "netagent_knowledge_base"
_TOP_K = 4


@functools.lru_cache(maxsize=1)
def _get_store() -> Chroma:
    return Chroma(
        collection_name=_COLLECTION_NAME,
        embedding_function=get_embeddings(),
        persist_directory=str(_PERSIST_DIR),
    )


@tool
async def search_knowledge_base(query: str) -> str:
    """Search the Open5GS/5G reference knowledge base for background on NF
    behavior, attach/session failure modes, subscriber profile fields,
    slicing (S-NSSAI), or how to interpret NF logs and configs.

    Use this to confirm expected values or behavior when diagnosing an
    ambiguous failure — it grounds an answer in reference material rather
    than relying on memory alone.
    """
    if not _PERSIST_DIR.exists():
        return (
            "The knowledge base has not been built yet. Run "
            "`scripts/build_knowledge_base.py` to seed it."
        )

    store = _get_store()
    results = store.similarity_search(query, k=_TOP_K)
    if not results:
        return "No relevant knowledge base entries found for this query."

    sections = [
        f"[{doc.metadata.get('source', 'unknown')}]\n{doc.page_content}"
        for doc in results
    ]
    return "\n\n---\n\n".join(sections)
