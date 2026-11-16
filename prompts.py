"""Prompt templates and formatting utilities for RepoChat."""

from dataclasses import dataclass
from typing import Any


SYSTEM_PROMPT: str = (
    "You are RepoChat, an expert AI assistant that explains GitHub repositories simply and clearly.\n\n"
    "Strict Rules:\n"
    "1. Answer primarily using the provided repository context chunks. Use your internal knowledge only to connect concepts or provide basic programming context.\n"
    "2. If the context is completely missing or irrelevant to the question, "
    'respond with: "not found in the repository".\n'
    "3. For high-level questions (e.g., 'what does this project do?'), synthesize an overview based on the provided README or documentation chunks.\n"
    "4. Think step by step internally before composing your concise response.\n"
    "5. Always cite the relevant file path(s) (e.g. `path/to/file.py`) from the context chunks.\n"
    "6. Keep the explanation accessible, practical, and direct."
)


def format_context_chunks(chunks: list[Any], max_chunks: int = 5) -> str:
    """Format up to max_chunks context chunks into a clean prompt block."""
    selected_chunks = chunks[:max_chunks]
    if not selected_chunks:
        return "No relevant repository context found."

    formatted_parts: list[str] = []
    for idx, c in enumerate(selected_chunks, start=1):
        if isinstance(c, dict):
            file_path = c.get("file_path", "unknown")
            heading = c.get("heading", "")
            text = c.get("text", "")
            language = c.get("language", "")
        else:
            file_path = getattr(c, "file_path", "unknown")
            heading = getattr(c, "heading", "")
            text = getattr(c, "text", "")
            language = getattr(c, "language", "")

        header = f"--- Chunk {idx} | File: {file_path}"
        if heading:
            header += f" | Section: {heading}"
        if language:
            header += f" ({language})"
        header += " ---"

        formatted_parts.append(f"{header}\n{text.strip()}")

    return "\n\n".join(formatted_parts)


def format_chat_history(chat_history: list[dict[str, str]] | None, max_turns: int = 4) -> str:
    """Format only the last max_turns chat turns into text."""
    if not chat_history:
        return ""

    recent_turns = chat_history[-max_turns:]
    history_lines: list[str] = []
    for turn in recent_turns:
        role = turn.get("role", "user").capitalize()
        content = turn.get("content", "").strip()
        history_lines.append(f"{role}: {content}")

    return "\n".join(history_lines)


def build_rag_prompt(
    query: str,
    chunks: list[Any],
    chat_history: list[dict[str, str]] | None = None,
    max_chunks: int = 5,
    max_turns: int = 4,
    best_effort: bool = False,
) -> str:
    """Construct full RAG prompt incorporating context chunks and recent chat history."""
    context_str = format_context_chunks(chunks, max_chunks=max_chunks)
    history_str = format_chat_history(chat_history, max_turns=max_turns)

    # Use a slightly more flexible system prompt for "best effort" high-level queries
    current_system_prompt = SYSTEM_PROMPT
    if best_effort:
        current_system_prompt = (
            "You are RepoChat, an expert AI assistant that explains GitHub repositories. "
            "You are currently answering a high-level project summary question. "
            "Use the provided context to give the most helpful overview possible. "
            "If the context is limited, synthesize a helpful response based on the available file names and snippets, "
            "but still cite your sources. Only say 'not found' if the context is completely empty."
        )

    sections: list[str] = [current_system_prompt]
    if history_str:
        sections.append(f"Conversation History (last {max_turns} turns):\n{history_str}")

    sections.append(f"Repository Context:\n{context_str}")
    sections.append(f"User Question:\n{query.strip()}")
    sections.append("Answer (remember to cite source file paths and explain simply):")

    return "\n\n".join(sections)
