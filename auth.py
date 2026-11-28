"""auth.py — Authentication helpers for RepoChat.

Stores users in a local SQLite database (users.db).
Passwords are hashed with bcrypt — never stored in plain text.
"""

from pathlib import Path
import json
import sqlite3
import bcrypt

# The database file is created automatically in the project folder.
DB_PATH = Path(__file__).resolve().parent / "users.db"


def _get_connection():
    """Open (or create) the SQLite database and return a connection."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    return conn


def _create_table():
    """Create the users and chat_history tables if they don't already exist."""
    conn = _get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT    NOT NULL UNIQUE,
            password TEXT    NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            username   TEXT NOT NULL,
            repo_key   TEXT NOT NULL,
            repo_url   TEXT NOT NULL,
            question   TEXT NOT NULL,
            answer     TEXT NOT NULL,
            sources    TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_history_user
        ON chat_history (username, id)
    """)
    conn.commit()
    conn.close()


# Create the table when this module is first imported.
_create_table()


def create_user(username: str, password: str) -> tuple[bool, str]:
    """Register a new user.

    Args:
        username: The desired username (must be unique).
        password: Plain-text password (must be ≥ 6 characters).

    Returns:
        (True, "")          on success.
        (False, error_msg)  if validation fails or the username is taken.
    """
    # --- Validation ---
    username = username.strip()
    if not username:
        return False, "Username cannot be empty."
    if not password:
        return False, "Password cannot be empty."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."

    # --- Hash the password ---
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    # --- Insert into the database ---
    try:
        conn = _get_connection()
        existing = conn.execute(
            "SELECT 1 FROM users WHERE LOWER(username) = LOWER(?)", (username,)
        ).fetchone()
        if existing:
            conn.close()
            return False, f'Username "{username}" is already taken. Please choose another.'

        conn.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, hashed),
        )
        conn.commit()
        conn.close()
        return True, ""
    except sqlite3.IntegrityError:
        # UNIQUE constraint failed → username already taken
        return False, f'Username "{username}" is already taken. Please choose another.'


def verify_user(username: str, password: str) -> tuple[bool, str]:
    """Check login credentials.

    Args:
        username: The username to look up.
        password: The plain-text password to verify.

    Returns:
        (True, "")          if credentials are correct.
        (False, error_msg)  otherwise.
    """
    username = username.strip()
    if not username or not password:
        return False, "Please fill in both fields."

    conn = _get_connection()
    row = conn.execute(
        "SELECT password FROM users WHERE LOWER(username) = LOWER(?)", (username,)
    ).fetchone()
    conn.close()

    if row is None:
        return False, "No account found with that username."

    # bcrypt.checkpw compares the plain password against the stored hash.
    stored_hash = row[0].encode()
    if bcrypt.checkpw(password.encode(), stored_hash):
        return True, ""
    else:
        return False, "Incorrect password. Please try again."


# ──────────────────────────────────────────────
# Per-user chat history
# ──────────────────────────────────────────────
def save_chat_turn(
    username: str,
    repo_key: str,
    repo_url: str,
    question: str,
    answer: str,
    sources: list[str],
) -> None:
    """Persist one answered question for a user. Parameterised query only."""
    conn = _get_connection()
    conn.execute(
        "INSERT INTO chat_history (username, repo_key, repo_url, question, answer, sources) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (username, repo_key, repo_url, question, answer, json.dumps(sources)),
    )
    conn.commit()
    conn.close()


def load_chat_history(username: str) -> list[dict]:
    """Return this user's saved turns, newest first. Never reads other users."""
    conn = _get_connection()
    rows = conn.execute(
        "SELECT id, repo_key, repo_url, question, answer, sources, created_at "
        "FROM chat_history WHERE username = ? ORDER BY id DESC",
        (username,),
    ).fetchall()
    conn.close()
    keys = ("id", "repo_key", "repo_url", "question", "answer", "sources", "created_at")
    return [dict(zip(keys, row)) for row in rows]


def delete_conversation(username: str, repo_key: str) -> None:
    """Delete this user's saved turns for one repository conversation."""
    conn = _get_connection()
    conn.execute(
        "DELETE FROM chat_history WHERE username = ? AND repo_key = ?",
        (username, repo_key),
    )
    conn.commit()
    conn.close()
