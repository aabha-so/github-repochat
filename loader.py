"""Loader module to fetch and filter public GitHub repository files via codeload zip."""

import io
import re
import zipfile
from dataclasses import dataclass
from typing import Optional
import requests

from config import (
    GITHUB_TOKEN,
    IGNORED_DIRS,
    IGNORED_EXTENSIONS,
    IGNORED_FILENAMES,
    MAX_FILE_SIZE_BYTES,
    MAX_FILES,
)


class RepoTooLargeError(Exception):
    """Raised when repository exceeds the maximum file limit."""


class RepoLoaderError(Exception):
    """Raised when repository loading fails due to network or invalid URL."""


@dataclass
class LoadedFile:
    """Represents a text file loaded from a repository."""
    path: str
    content: str


def parse_github_url(url: str) -> tuple[str, str]:
    """Extract (owner, repo) from a GitHub repository URL."""
    clean_url = url.strip().rstrip("/")
    if clean_url.endswith(".git"):
        clean_url = clean_url[:-4]
    match = re.search(r"github\.com/([^/]+)/([^/]+)", clean_url)
    if not match:
        raise RepoLoaderError(f"Invalid GitHub URL: '{url}'. Expected format: https://github.com/owner/repo")
    return match.group(1), match.group(2)


def get_latest_commit_sha(owner: str, repo: str) -> str:
    """Fetch latest commit SHA for HEAD, falling back to 'HEAD' if unavailable."""
    api_url = f"https://api.github.com/repos/{owner}/{repo}/commits/HEAD"
    headers = {"User-Agent": "RepoChat", "Accept": "application/vnd.github.v3+json"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    try:
        resp = requests.get(api_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json().get("sha", "HEAD")
    except Exception:
        pass
    return "HEAD"


def _is_text_file(content_bytes: bytes) -> bool:
    """Check if file content is non-binary UTF-8 text."""
    if b"\x00" in content_bytes:
        return False
    try:
        content_bytes.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def load_repository(repo_url: str) -> tuple[list[LoadedFile], str, str, str]:
    """Download repo zip and return (files, owner, repo, commit_sha)."""
    owner, repo = parse_github_url(repo_url)
    commit_sha = get_latest_commit_sha(owner, repo)
    codeload_url = f"https://codeload.github.com/{owner}/{repo}/zip/{commit_sha}"

    headers = {"User-Agent": "RepoChat"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"token {GITHUB_TOKEN}"

    try:
        resp = requests.get(codeload_url, headers=headers, timeout=30)
    except Exception as exc:
        raise RepoLoaderError(f"Failed to connect to GitHub codeload: {exc}") from exc

    if resp.status_code != 200:
        raise RepoLoaderError(f"GitHub returned HTTP {resp.status_code} for {codeload_url}")

    try:
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
    except zipfile.BadZipFile as exc:
        raise RepoLoaderError("Downloaded payload is not a valid zip archive.") from exc

    loaded_files: list[LoadedFile] = []
    for info in zf.infolist():
        if info.is_dir():
            continue

        parts = info.filename.split("/")
        # Skip root archive directory
        if len(parts) <= 1:
            continue
        rel_path = "/".join(parts[1:])
        lower_parts = [p.lower() for p in parts[1:]]

        # Filter directories and lockfiles
        if any(p in IGNORED_DIRS for p in lower_parts[:-1]):
            continue
        filename = lower_parts[-1]
        if filename in IGNORED_FILENAMES:
            continue

        # Filter extensions and size
        if any(filename.endswith(ext) for ext in IGNORED_EXTENSIONS):
            continue
        if info.file_size > MAX_FILE_SIZE_BYTES or info.file_size == 0:
            continue

        raw = zf.read(info)
        if not _is_text_file(raw):
            continue

        loaded_files.append(LoadedFile(path=rel_path, content=raw.decode("utf-8", errors="replace")))
        if len(loaded_files) > MAX_FILES:
            raise RepoTooLargeError(
                f"Repository '{owner}/{repo}' exceeds the limit of {MAX_FILES} files. "
                "RepoChat only indexes small to medium repositories."
            )

    return loaded_files, owner, repo, commit_sha
