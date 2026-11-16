"""Chunker module for recursive text chunking and metadata extraction."""

from dataclasses import dataclass
from pathlib import Path
import re
from loader import LoadedFile

# Extension to language mapping
EXT_TO_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".html": "html",
    ".css": "css",
    ".json": "json",
    ".md": "markdown",
    ".rst": "restructuredtext",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".toml": "toml",
    ".sh": "shell",
    ".bash": "shell",
    ".sql": "sql",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".rs": "rust",
    ".go": "go",
    ".java": "java",
}


@dataclass
class Chunk:
    """Represents a text chunk with metadata."""
    chunk_id: str
    text: str
    file_path: str
    language: str
    heading: str


def detect_language(file_path: str) -> str:
    """Detect programming language from file extension."""
    suffix = Path(file_path).suffix.lower()
    return EXT_TO_LANG.get(suffix, "text")


def extract_heading(text: str, language: str) -> str:
    """Extract section heading, markdown header, or class/function signature."""
    if language == "markdown":
        match = re.search(r"^#{1,6}\s+(.+)$", text, re.MULTILINE)
        if match:
            return match.group(1).strip()
    match = re.search(r"^\s*(?:def|class|function|interface|pub fn)\s+([A-Za-z0-9_]+)", text, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return ""


def recursive_split_text(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
    separators: list[str] | None = None,
) -> list[str]:
    """Recursively split text into segments within chunk_size with overlap."""
    if separators is None:
        separators = ["\n\n", "\n", ". ", " ", ""]

    if len(text) <= chunk_size or not separators:
        return [text.strip()] if text.strip() else []

    sep = separators[0]
    next_separators = separators[1:]
    parts = text.split(sep) if sep else list(text)

    merged_chunks: list[str] = []
    current_chunk = ""

    for part in parts:
        candidate = f"{current_chunk}{sep}{part}" if current_chunk else part
        if len(candidate) <= chunk_size:
            current_chunk = candidate
        else:
            if current_chunk.strip():
                merged_chunks.append(current_chunk.strip())
            if len(part) > chunk_size and next_separators:
                sub_chunks = recursive_split_text(part, chunk_size, chunk_overlap, next_separators)
                merged_chunks.extend(sub_chunks)
                current_chunk = ""
            else:
                # Add overlap from the tail of current_chunk if applicable
                overlap_prefix = current_chunk[-chunk_overlap:] if len(current_chunk) >= chunk_overlap else current_chunk
                current_chunk = f"{overlap_prefix}{sep}{part}" if overlap_prefix else part

    if current_chunk.strip():
        merged_chunks.append(current_chunk.strip())

    return [c for c in merged_chunks if c]


def chunk_files(
    files: list[LoadedFile],
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> list[Chunk]:
    """Process loaded files into metadata-tagged chunks."""
    all_chunks: list[Chunk] = []

    for file in files:
        language = detect_language(file.path)
        splits = recursive_split_text(file.content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        current_heading = ""

        for idx, split_text in enumerate(splits):
            found_heading = extract_heading(split_text, language)
            if found_heading:
                current_heading = found_heading

            chunk_id = f"{file.path}#chunk_{idx}"
            all_chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    text=split_text,
                    file_path=file.path,
                    language=language,
                    heading=current_heading,
                )
            )

    return all_chunks
