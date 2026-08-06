import sqlite3

import pytest

from app.core.security import hash_password, verify_password
from scripts.rotate_local_admin import rotate_admin_connection


def test_rotate_admin_connection_replaces_password_and_revokes_sessions() -> None:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            updated_at DATETIME
        );
        CREATE TABLE user_sessions (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL
        );
        """
    )
    old_hash, old_salt = hash_password("1234")
    connection.execute(
        "INSERT INTO users (id, username, password_salt, password_hash) VALUES (?, ?, ?, ?)",
        (7, "madao", old_salt, old_hash),
    )
    connection.executemany(
        "INSERT INTO user_sessions (user_id, token) VALUES (?, ?)",
        [(7, "one"), (7, "two")],
    )
    connection.commit()

    result = rotate_admin_connection(connection, "madao", "N3w-Local!Admin-2026")

    stored_salt, stored_hash = connection.execute(
        "SELECT password_salt, password_hash FROM users WHERE id = 7"
    ).fetchone()
    assert not verify_password("1234", stored_salt, stored_hash)
    assert verify_password("N3w-Local!Admin-2026", stored_salt, stored_hash)
    assert connection.execute(
        "SELECT COUNT(*) FROM user_sessions WHERE user_id = 7"
    ).fetchone()[0] == 0
    assert result == {"user_id": 7, "revoked_sessions": 2}


def test_rotate_admin_connection_requires_existing_user() -> None:
    connection = sqlite3.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            updated_at DATETIME
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE user_sessions (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL
        )
        """
    )

    with pytest.raises(LookupError, match="does not exist"):
        rotate_admin_connection(connection, "missing", "N3w-Local!Admin-2026")
