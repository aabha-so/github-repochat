"""Evaluation script for RepoChat.

Evaluates 15 fixed questions across README, setup, library, and function types.
Computes:
1. Precision@5: Fraction of retrieved top-5 chunks containing expected ground-truth files.
2. Groundedness check: Verifies all cited file paths in the LLM answer appear in retrieved chunks.
3. Latency: Compares average latency with hybrid retrieval vs direct baseline generation.
"""

from dataclasses import dataclass
from pathlib import Path
import re
import sys
import time
from typing import Any

from chromadb.api.models.Collection import Collection

from indexer import index_repository
from loader import LoadedFile
from prompts import build_rag_prompt
from retriever import ask_groq, hybrid_search


@dataclass
class EvalSample:
    """Evaluation test sample."""
    question: str
    category: str  # 'readme', 'setup', 'library', 'function'
    expected_files: list[str]


# 15 fixed benchmark questions
EVAL_DATASET: list[EvalSample] = [
    # README questions (4)
    EvalSample("What is this repository about?", "readme", ["README.md"]),
    EvalSample("What project overview is provided?", "readme", ["README.md"]),
    EvalSample("How do I run the main application from the command line?", "readme", ["README.md"]),
    EvalSample("What are the features described in the documentation?", "readme", ["README.md"]),
    # Setup questions (3)
    EvalSample("How do I install the project dependencies?", "setup", ["requirements.txt", "README.md"]),
    EvalSample("What packages are required in requirements.txt?", "setup", ["requirements.txt"]),
    EvalSample("Is numpy listed as a project dependency?", "setup", ["requirements.txt"]),
    # Library questions (4)
    EvalSample("What math calculator utilities are implemented?", "library", ["src/calculator.py"]),
    EvalSample("How does the add function work?", "library", ["src/calculator.py"]),
    EvalSample("Where is the multiply method defined?", "library", ["src/calculator.py"]),
    EvalSample("What exception does divide throw when dividing by zero?", "library", ["src/calculator.py"]),
    # Function questions (4)
    EvalSample("Where is the main entry point defined?", "function", ["main.py"]),
    EvalSample("How does main invoke the Calculator class?", "function", ["main.py"]),
    EvalSample("What calculation is executed when running main.py?", "function", ["main.py"]),
    EvalSample("How is the Calculator imported in main.py?", "function", ["main.py"]),
]


def extract_cited_files(answer: str) -> list[str]:
    """Extract backtick-enclosed file paths mentioned in generated answer."""
    pattern = r"`([a-zA-Z0-9_\-\./\\]+\.[a-zA-Z0-9]+)`"
    matches = re.findall(pattern, answer)
    return list(dict.fromkeys(matches))


def check_groundedness(cited_files: list[str], retrieved_files: list[str]) -> bool:
    """Plain-code verification: all cited files must exist in retrieved chunks."""
    if not cited_files:
        return True
    retrieved_set = set(retrieved_files)
    return all(c in retrieved_set for c in cited_files)


def run_evaluation(collection: Collection, run_llm: bool = True) -> dict[str, Any]:
    """Run evaluation benchmark over the 15 fixed questions."""
    precision_scores: list[float] = []
    groundedness_scores: list[bool] = []
    retrieval_latencies: list[float] = []
    rag_latencies: list[float] = []
    direct_latencies: list[float] = []

    for sample in EVAL_DATASET:
        t0 = time.perf_counter()
        chunks = hybrid_search(sample.question, collection, top_k=5)
        retrieval_time = time.perf_counter() - t0
        retrieval_latencies.append(retrieval_time)

        retrieved_files = [c.file_path for c in chunks]
        # Precision@5: hits / 5
        hits = sum(1 for f in retrieved_files if f in sample.expected_files)
        precision_at_5 = hits / 5.0
        precision_scores.append(precision_at_5)

        if run_llm:
            # Full RAG latency
            t1 = time.perf_counter()
            prompt = build_rag_prompt(sample.question, chunks)
            ans = ask_groq(prompt)
            rag_latencies.append(time.perf_counter() - t1 + retrieval_time)

            cited = extract_cited_files(ans)
            grounded = check_groundedness(cited, retrieved_files)
            groundedness_scores.append(grounded)

            # Direct latency baseline (no retrieval)
            t2 = time.perf_counter()
            _ = ask_groq(f"Answer briefly: {sample.question}")
            direct_latencies.append(time.perf_counter() - t2)

    avg_precision = sum(precision_scores) / len(precision_scores)
    grounded_rate = sum(groundedness_scores) / len(groundedness_scores) if groundedness_scores else 1.0
    avg_rag_latency = sum(rag_latencies) / len(rag_latencies) if rag_latencies else 0.0
    avg_direct_latency = sum(direct_latencies) / len(direct_latencies) if direct_latencies else 0.0

    return {
        "total_questions": len(EVAL_DATASET),
        "precision_at_5": round(avg_precision, 4),
        "groundedness_rate": round(grounded_rate, 4),
        "avg_rag_latency_sec": round(avg_rag_latency, 3),
        "avg_direct_latency_sec": round(avg_direct_latency, 3),
    }


if __name__ == "__main__":
    print("eval.py module loaded. Run tests/test_stage6.py to execute the evaluation suite.")
