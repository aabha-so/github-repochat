"""Global configuration and constants for RepoChat."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Disable ChromaDB telemetry to prevent PostHog telemetry errors
os.environ["ANONYMIZED_TELEMETRY"] = "False"
try:
    import logging
    logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)
    import chromadb.telemetry.product.posthog as _chroma_posthog
    _chroma_posthog.Posthog.capture = lambda *args, **kwargs: None
    if hasattr(_chroma_posthog, "ProductTelemetryClient"):
        _chroma_posthog.ProductTelemetryClient.capture = lambda *args, **kwargs: None
except Exception:
    pass

def _get_secret(key: str, default: str = "") -> str:
    """Read key from os.getenv or st.secrets (if deployed on Streamlit Cloud)."""
    val = os.getenv(key, "")
    if val:
        return val

    # In local development, .env is standard. Check st.secrets only if secrets file exists.
    try:
        from streamlit.runtime.secrets import secrets_singleton
        file_paths = getattr(secrets_singleton, "_file_paths", [])
        if any(Path(p).is_file() for p in file_paths):
            import streamlit as st
            if key in st.secrets:
                return str(st.secrets[key])
    except Exception:
        pass
    return default


# API Keys and tokens
GROQ_API_KEY: str = _get_secret("GROQ_API_KEY", "")
GITHUB_TOKEN: str = _get_secret("GITHUB_TOKEN", "")

# LLM & Embedding Settings
GROQ_MODEL: str = "openai/gpt-oss-120b"
EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

# Ingestion constraints
MAX_FILES: int = 300
MAX_FILE_SIZE_BYTES: int = 100 * 1024  # 100 KB
INDEX_DIR: Path = Path("./index")

# Ignored directory names
IGNORED_DIRS: set[str] = {
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    "env",
    ".idea",
    ".vscode",
    "dist",
    "build",
    ".egg-info",
}

# Ignored extensions (binaries, media, archives, compiled files)
IGNORED_EXTENSIONS: set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".zip", ".tar", ".gz", ".7z", ".rar",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a",
    ".pyc", ".pyo", ".pyd", ".class",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
}

# Ignored lockfiles
IGNORED_FILENAMES: set[str] = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "cargo.lock",
    "pipfile.lock",
    "composer.lock",
    "gemfile.lock",
}

if __name__ == "__main__":
    print("=== RepoChat Configuration ===")
    print(f"GROQ_MODEL: {GROQ_MODEL}")
    print(f"EMBEDDING_MODEL: {EMBEDDING_MODEL}")
    print(f"GROQ_API_KEY: {'[Configured]' if GROQ_API_KEY else '[Missing in .env]'}")
    print(f"GITHUB_TOKEN: {'[Configured]' if GITHUB_TOKEN else '[Optional - Not set]'}")
    print(f"MAX_FILES: {MAX_FILES}")
    print(f"MAX_FILE_SIZE: {MAX_FILE_SIZE_BYTES // 1024} KB")
    print("Config loaded successfully with no errors.")

