"""Retriever module providing hybrid search and Gemini RAG answers."""

from dataclasses import dataclass
import re
import time
from typing import Any
from chromadb.api.models.Collection import Collection
from groq import Groq
import numpy as np
from rank_bm25 import BM25Okapi

from config import GROQ_API_KEY, GROQ_MODEL
from indexer import get_embedding_model
from prompts import SYSTEM_PROMPT, build_rag_prompt

# In-memory question cache (kept for test compatibility; not actively used during tuning)
_QUESTION_CACHE: dict[tuple[str, str], tuple[str, list["RetrievedChunk"]]] = {}
_GROQ_CLIENT: Groq | None = None


@dataclass
class RetrievedChunk:
    """Represents a chunk retrieved by hybrid search."""
    chunk_id: str
    text: str
    file_path: str
    language: str
    heading: str
    score: float


def tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase alphanumeric tokens for BM25."""
    return re.findall(r"\w+", text.lower())


def get_groq_client() -> Groq:
    """Get or create singleton Groq API client."""
    global _GROQ_CLIENT
    if _GROQ_CLIENT is None:
        _GROQ_CLIENT = Groq(api_key=GROQ_API_KEY)
    return _GROQ_CLIENT


def hybrid_search(query: str, collection: Collection, top_k: int = 5) -> list[RetrievedChunk]:
    """Combine dense ChromaDB semantic search and sparse BM25 with Reciprocal Rank Fusion."""
    all_data = collection.get(include=["documents", "metadatas"])
    doc_ids: list[str] = all_data.get("ids", [])
    documents: list[str] = all_data.get("documents", [])
    metadatas: list[dict[str, Any]] = all_data.get("metadatas", [])

    if not doc_ids:
        return []

    id_to_meta = {doc_ids[i]: (documents[i], metadatas[i]) for i in range(len(doc_ids))}

    # 1. Dense Semantic Search
    embed_model = get_embedding_model()
    query_emb = embed_model.encode([query]).tolist()[0]
    n_results = min(20, len(doc_ids))
    dense_res = collection.query(
        query_embeddings=[query_emb],
        n_results=n_results,
        include=["documents", "metadatas"],
    )
    dense_ids: list[str] = dense_res.get("ids", [[]])[0]
    dense_ranks = {cid: rank for rank, cid in enumerate(dense_ids, start=1)}

    # 2. Sparse BM25 Search
    corpus = [tokenize(doc) for doc in documents]
    bm25 = BM25Okapi(corpus)
    q_tokens = tokenize(query)
    sparse_ranks: dict[str, int] = {}
    if q_tokens:
        scores = bm25.get_scores(q_tokens)
        sorted_indices = np.argsort(scores)[::-1]
        ranked_candidates = [doc_ids[i] for i in sorted_indices[:20] if scores[i] > 0]
        sparse_ranks = {cid: rank for rank, cid in enumerate(ranked_candidates, start=1)}

    # 3. Reciprocal Rank Fusion (RRF)
    all_cids = set(dense_ranks.keys()) | set(sparse_ranks.keys())
    rrf_scores: dict[str, float] = {}
    for cid in all_cids:
        score = 0.0
        if cid in dense_ranks:
            score += 1.0 / (60.0 + dense_ranks[cid])
        if cid in sparse_ranks:
            score += 1.0 / (60.0 + sparse_ranks[cid])
        rrf_scores[cid] = score

    # Special Handling for high-level project questions:
    # Boost README.md chunks to ensure they are always present for "what does this do" queries
    high_level_keywords = {"what", "do", "project", "purpose", "overview", "goals", "about"}
    if any(word in query.lower() for word in high_level_keywords):
        for cid, (doc, meta) in id_to_meta.items():
            if "readme" in meta.get("file_path", "").lower():
                rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 0.5  # Significant boost

    top_cids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)[:top_k]

    return [
        RetrievedChunk(
            chunk_id=cid,
            text=id_to_meta[cid][0],
            file_path=id_to_meta[cid][1].get("file_path", "unknown"),
            language=id_to_meta[cid][1].get("language", "text"),
            heading=id_to_meta[cid][1].get("heading", ""),
            score=round(rrf_scores[cid], 5),
        )
        for cid in top_cids
        if cid in id_to_meta
    ]


def ask_groq(prompt: str, max_retries: int = 3, initial_delay: float = 2.0) -> str:
    """Send single prompt to Groq with exponential backoff on rate limits."""
    client = get_groq_client()

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            err = str(exc).lower()
            is_rate_error = any(k in err for k in ["429", "503", "unavailable", "rate", "quota"])
            if is_rate_error and attempt < max_retries - 1:
                delay = initial_delay * (2 ** attempt)
                time.sleep(delay)
                continue
            raise


# Alias for backward compatibility with graph.py
ask_gemini = ask_groq


def query_repo(
    query: str,
    collection: Collection,
    chat_history: list[dict[str, str]] | None = None,
    best_effort: bool = False,
) -> tuple[str, list[RetrievedChunk]]:
    """Hybrid search + single LLM call."""
    chunks = hybrid_search(query, collection, top_k=5)

    # FALLBACK: If no chunks were found, try to force-retrieve README snippets
    if not chunks:
        all_data = collection.get(include=["documents", "metadatas"])
        doc_ids = all_data.get("ids", [])
        documents = all_data.get("documents", [])
        metadatas = all_data.get("metadatas", [])

        readme_chunks = []
        for i in range(len(doc_ids)):
            if "readme" in metadatas[i].get("file_path", "").lower():
                readme_chunks.append(
                    RetrievedChunk(
                        chunk_id=doc_ids[i],
                        text=documents[i],
                        file_path=metadatas[i].get("file_path", "unknown"),
                        language=metadatas[i].get("language", "text"),
                        heading=metadatas[i].get("heading", ""),
                        score=0.1
                    )
                )
        # Take the first 5 README chunks as a last resort
        chunks = readme_chunks[:5]

    prompt = build_rag_prompt(query, chunks, chat_history=chat_history, max_chunks=5, max_turns=4, best_effort=best_effort)
    answer = ask_groq(prompt)

    return answer, chunks
