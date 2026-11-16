"""Graph module implementing LangGraph workflow for RepoChat.

Flow: route -> retrieve -> grade -> (generate | rewrite -> retrieve -> generate)
Router & Grade use no LLM. Query rewritten at most once. Memory via MemorySaver.
"""

from typing import Any, Literal, TypedDict
from chromadb.api.models.Collection import Collection
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from prompts import build_rag_prompt
from retriever import RetrievedChunk, ask_gemini, hybrid_search

SCORE_THRESHOLD: float = 0.015
GREETING_KEYWORDS = {"hi", "hello", "hey", "who are you", "help", "thanks", "thank you"}


class AgentState(TypedDict):
    """LangGraph state representation for RepoChat."""
    query: str
    original_query: str
    index_path: str
    chat_history: list[dict[str, str]]
    chunks: list[dict[str, Any]]
    is_direct: bool
    rewrite_count: int
    answer: str


def route_node(state: AgentState) -> dict[str, Any]:
    """Route input based on keywords without using an LLM."""
    query_clean = state["query"].strip().lower().rstrip("!?.")
    return {"is_direct": query_clean in GREETING_KEYWORDS}


def retrieve_node(state: AgentState) -> dict[str, Any]:
    """Retrieve top-5 chunks using hybrid search."""
    import chromadb
    from chromadb.config import Settings
    client = chromadb.PersistentClient(
        path=state["index_path"],
        settings=Settings(anonymized_telemetry=False),
    )
    collection = client.get_or_create_collection(name="repo_chunks")
    chunks = hybrid_search(state["query"], collection, top_k=5)
    serialized = [
        {"chunk_id": c.chunk_id, "text": c.text, "file_path": c.file_path,
         "language": c.language, "heading": c.heading, "score": c.score}
        for c in chunks
    ]
    return {"chunks": serialized}


def grade_node(state: AgentState) -> dict[str, Any]:
    """Check if retrieved chunks meet similarity threshold (no LLM)."""
    chunks = state.get("chunks", [])
    scores = [(c.score if hasattr(c, "score") else c.get("score", 0.0)) for c in chunks]
    max_score = max(scores, default=0.0)
    return {"needs_rewrite": not (chunks and max_score >= SCORE_THRESHOLD)}


def rewrite_node(state: AgentState) -> dict[str, Any]:
    """Deterministically rewrite query ONCE to improve keyword retrieval."""
    q = state["original_query"]
    for prefix in ["can you explain", "how do i", "where is", "tell me about", "what is"]:
        if q.lower().startswith(prefix):
            q = q[len(prefix):].strip()
            break
    return {"query": q, "rewrite_count": state.get("rewrite_count", 0) + 1}


def generate_node(state: AgentState) -> dict[str, Any]:
    """Generate direct greeting or single Gemini call grounded in retrieved chunks."""
    if state.get("is_direct", False):
        return {
            "answer": "Hello! I am RepoChat. Ask me any question about this codebase, "
                      "and I will answer using only the repository's files with citations."
        }
    raw_chunks = state.get("chunks", [])
    chunks = [
        c if isinstance(c, RetrievedChunk) else RetrievedChunk(
            chunk_id=c["chunk_id"], text=c["text"], file_path=c["file_path"],
            language=c["language"], heading=c["heading"], score=c["score"]
        )
        for c in raw_chunks
    ]
    prompt = build_rag_prompt(
        query=state["original_query"], chunks=chunks,
        chat_history=state.get("chat_history", []), max_chunks=5, max_turns=4
    )
    return {"answer": ask_gemini(prompt)}


def should_route(state: AgentState) -> Literal["generate", "retrieve"]:
    return "generate" if state.get("is_direct") else "retrieve"


def should_grade(state: AgentState) -> Literal["rewrite", "generate"]:
    if state.get("needs_rewrite", False) and state.get("rewrite_count", 0) < 1:
        return "rewrite"
    return "generate"


def build_repo_graph() -> tuple[Any, MemorySaver]:
    """Construct and compile the LangGraph workflow with MemorySaver checkpointer."""
    workflow = StateGraph(AgentState)
    workflow.add_node("route", route_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("grade", grade_node)
    workflow.add_node("rewrite", rewrite_node)
    workflow.add_node("generate", generate_node)

    workflow.add_edge(START, "route")
    workflow.add_conditional_edges("route", should_route, {"generate": "generate", "retrieve": "retrieve"})
    workflow.add_edge("retrieve", "grade")
    workflow.add_conditional_edges("grade", should_grade, {"rewrite": "rewrite", "generate": "generate"})
    workflow.add_edge("rewrite", "retrieve")
    workflow.add_edge("generate", END)

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer), checkpointer
