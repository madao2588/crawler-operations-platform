from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from app.core.security import hash_password, verify_password
from scripts.build_intranet_package import (
    generate_env_safe_password,
    prepare_release_database,
    write_production_env,
)


def _create_auth_database(path: Path) -> None:
    password_hash, password_salt = hash_password("123456")
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                password_salt TEXT NOT NULL,
                updated_at DATETIME
            );
            CREATE TABLE user_sessions (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                token TEXT NOT NULL
            );
            CREATE TABLE collected_data (id INTEGER PRIMARY KEY, title TEXT);
            """
        )
        connection.execute(
            """
            INSERT INTO users (id, username, password_hash, password_salt)
            VALUES (1, 'admin', ?, ?)
            """,
            (password_hash, password_salt),
        )
        connection.execute(
            "INSERT INTO user_sessions (user_id, token) VALUES (1, 'old-session')"
        )
        connection.execute("INSERT INTO collected_data (title) VALUES ('保留数据')")


def test_generated_release_password_is_strong_and_env_safe() -> None:
    password = generate_env_safe_password()

    assert len(password) == 24
    assert any(char.islower() for char in password)
    assert any(char.isupper() for char in password)
    assert any(char.isdigit() for char in password)
    assert any(char in "!@%_-" for char in password)
    assert not any(char in "#$'\"` \t\r\n" for char in password)


def test_release_database_is_consistent_rotated_and_session_free(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    destination = tmp_path / "release.db"
    _create_auth_database(source)
    new_password = "Strong-Release_2026!A"

    summary = prepare_release_database(
        source,
        destination,
        username="admin",
        password=new_password,
    )

    assert summary == {"users": 1, "notices": 1, "revoked_sessions": 1}
    with sqlite3.connect(destination) as connection:
        password_hash, password_salt = connection.execute(
            "SELECT password_hash, password_salt FROM users WHERE username = 'admin'"
        ).fetchone()
        assert verify_password(new_password, password_salt, password_hash)
        assert connection.execute("SELECT COUNT(*) FROM user_sessions").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM collected_data").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    with sqlite3.connect(source) as connection:
        assert connection.execute("SELECT COUNT(*) FROM user_sessions").fetchone()[0] == 1


def test_production_env_contains_literal_generated_password(tmp_path: Path) -> None:
    destination = tmp_path / ".env.production"
    password = "Strong-Release_2026!A"

    write_production_env(destination, username="admin", password=password, port=8093)

    content = destination.read_text(encoding="utf-8")
    assert f"CRAWLER_BOOTSTRAP_ADMIN_PASSWORD={password}" in content
    assert "INTRANET_BIND_ADDRESS=0.0.0.0" in content
    assert "INTRANET_PORT=8093" in content
    assert "CRAWLER_STARTUP_CATCH_UP_ENABLED=true" in content
    assert "replace-with" not in content


@pytest.mark.skipif(os.name != "nt", reason="PowerShell deployment script is Windows-specific")
def test_release_version_sync_preserves_active_configuration(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe")
    assert powershell is not None
    common = tmp_path / "_common.ps1"
    source = Path(__file__).resolve().parents[2] / "deployment" / "intranet" / "_common.ps1"
    shutil.copy2(source, common)
    (tmp_path / ".env.production.initial").write_text(
        "INTRANET_PORT=8093\nRELEASE_VERSION=initial\n",
        encoding="utf-8",
    )
    (tmp_path / ".env.production").write_text(
        "INTRANET_PORT=18093\nCRAWLER_OUTBOUND_PROXY_URL=http://proxy.internal:8080\n"
        "RELEASE_VERSION=old-release\n",
        encoding="utf-8",
    )
    (tmp_path / "VERSION.json").write_text(
        json.dumps({"release_version": "new-release"}),
        encoding="utf-8",
    )

    escaped = str(common).replace("'", "''")
    subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            f". '{escaped}'; Initialize-Environment; Sync-ReleaseVersion",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    content = (tmp_path / ".env.production").read_text(encoding="utf-8")
    assert "INTRANET_PORT=18093" in content
    assert "CRAWLER_OUTBOUND_PROXY_URL=http://proxy.internal:8080" in content
    assert "RELEASE_VERSION=new-release" in content
    assert "RELEASE_VERSION=old-release" not in content


def test_deploy_script_passes_detached_mode_as_a_literal_compose_argument() -> None:
    deploy = (
        Path(__file__).resolve().parents[2]
        / "deployment"
        / "intranet"
        / "deploy.ps1"
    ).read_text(encoding="utf-8")

    assert 'Invoke-Compose -Arguments @("up", "-d", "--no-build"' in deploy
    assert 'Invoke-Compose -Arguments @("up", "-d", "--remove-orphans")' in deploy
    assert "Invoke-Compose up -d" not in deploy
