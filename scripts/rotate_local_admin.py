from __future__ import annotations

import argparse
import json
import secrets
import sqlite3
import string
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.core.security import hash_password

SPECIAL_CHARACTERS = "!@#$%^&*_-"


def generate_password(length: int = 24) -> str:
    if length < 16:
        raise ValueError("generated passwords must contain at least 16 characters")
    required = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice(SPECIAL_CHARACTERS),
    ]
    alphabet = string.ascii_letters + string.digits + SPECIAL_CHARACTERS
    required.extend(secrets.choice(alphabet) for _ in range(length - len(required)))
    secrets.SystemRandom().shuffle(required)
    return "".join(required)


def rotate_admin_connection(
    connection: sqlite3.Connection,
    username: str,
    password: str,
) -> dict[str, int]:
    if len(password) < 16:
        raise ValueError("password must contain at least 16 characters")
    row = connection.execute(
        "SELECT id FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if row is None:
        raise LookupError(f"local user {username!r} does not exist")

    user_id = int(row[0])
    password_hash, password_salt = hash_password(password)
    cursor = connection.execute(
        """
        UPDATE users
        SET password_hash = ?, password_salt = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (password_hash, password_salt, user_id),
    )
    if cursor.rowcount != 1:
        connection.rollback()
        raise RuntimeError(f"failed to rotate password for user {username!r}")
    revoked_sessions = connection.execute(
        "DELETE FROM user_sessions WHERE user_id = ?",
        (user_id,),
    ).rowcount
    connection.commit()
    return {
        "user_id": user_id,
        "revoked_sessions": max(0, int(revoked_sessions)),
    }


def backup_database(database_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = database_path.with_name(
        f"{database_path.stem}.before-admin-rotation.{timestamp}{database_path.suffix}"
    )
    with sqlite3.connect(database_path) as source, sqlite3.connect(backup_path) as target:
        source.backup(target)
    return backup_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rotate a local crawler administrator password and revoke its sessions."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=SERVER_DIR / "data.db",
        help="SQLite database path (default: server/data.db)",
    )
    parser.add_argument("--username", default="madao")
    parser.add_argument(
        "--password",
        help="New password. Omit to generate a cryptographically random password.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    database_path = args.database.expanduser().resolve()
    if not database_path.is_file():
        raise FileNotFoundError(f"database does not exist: {database_path}")
    password = args.password or generate_password()
    backup_path = backup_database(database_path)
    with sqlite3.connect(database_path) as connection:
        result = rotate_admin_connection(connection, args.username, password)
    print(
        json.dumps(
            {
                "username": args.username,
                "password": password,
                "database": str(database_path),
                "backup": str(backup_path),
                **result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
