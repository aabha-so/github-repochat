"""Indexer module for embedding chunks and persisting to ChromaDB."""

from pathlib import Path
import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from chunker import Chunk, chunk_files
from config import EMBEDDING_MODEL, INDEX_DIR
from loader import LoadedFile
import streamlit as st


@st.cache_resource
def _load_embedding_model() -> SentenceTransformer:
    """Load the embedding model once and cache it across all Streamlit sessions."""
    return SentenceTransformer(EMBEDDING_MODEL)


def get_embedding_model() -> SentenceTransformer:
    """Retrieve or initialize the cached SentenceTransformer embedding model."""
    return _load_embedding_model()


def get_index_path(owner: str, repo: str, commit_sha: str) -> Path:
    """Return persistent disk path for repository ChromaDB index."""
    safe_owner = owner.replace("/", "_").strip()
    safe_repo = repo.replace("/", "_").strip()
    return INDEX_DIR / f"{safe_owner}_{safe_repo}_{commit_sha}"


def is_index_cached(index_path: Path) -> bool:
    """Check if the persistent index directory exists and contains data."""
    if not index_path.exists():
        return False
    try:
        client = chromadb.PersistentClient(path=str(index_path))
        collections = client.list_collections()
        if not collections:
            return False
        col = client.get_collection(name=collections[0].name)
        return col.count() > 0
    except Exception:
        return False


def index_repository(
    files: list[LoadedFile],
    owner: str,
    repo: str,
    commit_sha: str,
    batch_size: int = 64,
) -> tuple[Collection, Path, bool]:
    """Index files into ChromaDB if not cached. Returns (collection, index_path, is_cached)."""
    index_path = get_index_path(owner, repo, commit_sha)

    client = chromadb.PersistentClient(
        path=str(index_path),
        settings=Settings(anonymized_telemetry=False),
    )
    if is_index_cached(index_path):
        collection = client.get_or_create_collection(name="repo_chunks")
        return collection, index_path, True

    index_path.mkdir(parents=True, exist_ok=True)
    collection = client.get_or_create_collection(name="repo_chunks")

    chunks: list[Chunk] = chunk_files(files)
    if not chunks:
        return collection, index_path, False

    embed_model = get_embedding_model()
    texts = [c.text for c in chunks]
    ids = [c.chunk_id for c in chunks]
    metadatas = [
        {"file_path": c.file_path, "language": c.language, "heading": c.heading}
        for c in chunks
    ]

    embeddings = embed_model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
    ).tolist()

    # Insert into ChromaDB in chunks of 500 to stay within limits
    step = 500
    for i in range(0, len(ids), step):
        collection.add(
            ids=ids[i : i + step],
            embeddings=embeddings[i : i + step],
            documents=texts[i : i + step],
            metadatas=metadatas[i : i + step],
        )

    return collection, index_path, False


if __name__ == "__main__":
    print("indexer.py loaded successfully. Run tests/test_stage2.py to verify indexing.")
