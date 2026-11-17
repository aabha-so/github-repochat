"""auth.py — Authentication helpers for RepoChat.

Stores users in a local SQLite database (users.db).
Passwords are hashed with bcrypt — never stored in plain text.
"""

import sqlite3
import bcrypt

# The database file is created automatically in the project folder.
DB_PATH = "users.db"


def _get_connection():
    """Open (or create) the SQLite database and return a connection."""
    conn = sqlite3.connect(DB_PATH)
    return conn


def _create_table():
    """Create the users table if it doesn't already exist."""
    conn = _get_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT    NOT NULL UNIQUE,
            password TEXT    NOT NULL
        )
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
        "SELECT password FROM users WHERE username = ?", (username,)
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
