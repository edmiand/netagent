"""Chunk knowledge_base/*.md, embed via Ollama, persist to a local Chroma store.

Rerun this after editing/adding any file under knowledge_base/ to refresh
the persisted vectors used by agent/tools/rag.py.
"""

from pathlib import Path

from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from agent.llm import get_embeddings

_ROOT = Path(__file__).parent.parent
_KB_DIR = _ROOT / "knowledge_base"
_PERSIST_DIR = _ROOT / "data" / "chroma"
_COLLECTION_NAME = "netagent_knowledge_base"


def main() -> None:
    md_files = sorted(_KB_DIR.glob("*.md"))
    if not md_files:
        raise SystemExit(f"No markdown files found in {_KB_DIR}")

    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=100)
    documents: list[Document] = []
    for path in md_files:
        text = path.read_text()
        for chunk in splitter.split_text(text):
            documents.append(Document(page_content=chunk, metadata={"source": path.name}))

    print(f"Loaded {len(md_files)} docs → {len(documents)} chunks")

    _PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    Chroma.from_documents(
        documents=documents,
        embedding=get_embeddings(),
        collection_name=_COLLECTION_NAME,
        persist_directory=str(_PERSIST_DIR),
    )
    print(f"Persisted {len(documents)} chunks to {_PERSIST_DIR}")


if __name__ == "__main__":
    main()
