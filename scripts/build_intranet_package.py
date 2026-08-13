from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import shutil
import sqlite3
import string
import subprocess
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "server"
BUILD_COMPOSE_FILE = REPO_ROOT / "compose.build.yml"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.core.security import hash_password

SAFE_SPECIAL_CHARACTERS = "!@%_-"
SOURCE_PATHS = (
    ".dockerignore",
    "compose.production.yml",
    "server/app",
    "server/Dockerfile",
    "server/main.py",
    "server/requirements.txt",
    "web/src",
    "web/Dockerfile.production",
    "web/index.html",
    "web/nginx.conf",
    "web/package.json",
    "web/package-lock.json",
    "web/tsconfig.app.json",
    "web/tsconfig.json",
    "web/tsconfig.node.json",
    "web/vite.config.ts",
    "docs/internal-operations.md",
    "docs/intranet-deployment.md",
)


def generate_env_safe_password(length: int = 24) -> str:
    if length < 16:
        raise ValueError("release passwords must contain at least 16 characters")
    required = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice(SAFE_SPECIAL_CHARACTERS),
    ]
    alphabet = string.ascii_letters + string.digits + SAFE_SPECIAL_CHARACTERS
    required.extend(secrets.choice(alphabet) for _ in range(length - len(required)))
    secrets.SystemRandom().shuffle(required)
    return "".join(required)


def prepare_release_database(
    source: Path,
    destination: Path,
    *,
    username: str,
    password: str,
) -> dict[str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as source_db,
        sqlite3.connect(destination) as release_db,
    ):
        source_db.backup(release_db)
        integrity = release_db.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise RuntimeError(f"release database integrity check failed: {integrity}")

        user = release_db.execute(
            "SELECT id FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        if user is None:
            raise LookupError(f"administrator {username!r} does not exist")
        password_hash, password_salt = hash_password(password)
        release_db.execute(
            """
            UPDATE users
            SET password_hash = ?, password_salt = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (password_hash, password_salt, int(user[0])),
        )
        revoked_sessions = int(
            release_db.execute("SELECT COUNT(*) FROM user_sessions").fetchone()[0]
        )
        release_db.execute("DELETE FROM user_sessions")
        users = int(release_db.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        notices = int(
            release_db.execute("SELECT COUNT(*) FROM collected_data").fetchone()[0]
        )
        release_db.commit()

    return {
        "users": users,
        "notices": notices,
        "revoked_sessions": revoked_sessions,
    }


def write_production_env(
    destination: Path,
    *,
    username: str,
    password: str,
    port: int,
    release_version: str = "latest",
) -> None:
    content = "\n".join(
        (
            f"CRAWLER_BOOTSTRAP_ADMIN_USERNAME={username}",
            f"CRAWLER_BOOTSTRAP_ADMIN_PASSWORD={password}",
            f"RELEASE_VERSION={release_version}",
            "INTRANET_BIND_ADDRESS=0.0.0.0",
            f"INTRANET_PORT={port}",
            "CRAWLER_OUTBOUND_PROXY_URL=",
            "CRAWLER_USE_SYSTEM_PROXY=true",
            "CRAWLER_OUTBOUND_NO_PROXY=localhost,127.0.0.1,::1,service.most.gov.cn,gdstc.gd.gov.cn,kjj.gz.gov.cn,www.hp.gov.cn,www.hengqin.gov.cn,kjt.hunan.gov.cn,kjj.changsha.gov.cn",
            "CRAWLER_CORS_ALLOWED_ORIGINS=",
            "CRAWLER_CORS_ALLOWED_ORIGIN_REGEX=",
            "CRAWLER_MAINTENANCE_ENABLED=true",
            "CRAWLER_STARTUP_CATCH_UP_ENABLED=true",
            "",
        )
    )
    destination.write_text(content, encoding="utf-8")


def _copy_path(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(
            source,
            destination,
            ignore=shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                "node_modules",
                "dist",
                "*.tsbuildinfo",
            ),
        )
    else:
        shutil.copy2(source, destination)


def _copy_release_sources(staging: Path) -> None:
    for relative in SOURCE_PATHS:
        source = REPO_ROOT / relative
        if not source.exists():
            raise FileNotFoundError(f"required release source is missing: {source}")
        _copy_path(source, staging / relative)
    for source in (REPO_ROOT / "deployment" / "intranet").iterdir():
        if source.is_file():
            shutil.copy2(source, staging / source.name)


def _copy_seed_storage(destination: Path) -> int:
    source = SERVER_DIR / "storage"
    if not source.is_dir():
        return 0
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    return sum(1 for path in destination.rglob("*") if path.is_file())


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _run(command: list[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def _build_offline_images(staging: Path, release_version: str) -> list[str]:
    env_file = staging / ".env.production.initial"
    compose_file = staging / "compose.production.yml"
    build_compose_file = staging / "compose.build.yml"
    shutil.copy2(BUILD_COMPOSE_FILE, build_compose_file)
    compose_prefix = [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(compose_file),
        "-f",
        str(build_compose_file),
    ]
    try:
        _run([*compose_prefix, "build", "--pull", "api"], cwd=staging)
        _run([*compose_prefix, "build", "--pull", "web"], cwd=staging)
        images = [
            f"new-drug-intelligence-api:{release_version}",
            f"new-drug-intelligence-web:{release_version}",
        ]
        image_dir = staging / "images"
        image_dir.mkdir(parents=True, exist_ok=True)
        _run(
            [
                "docker",
                "save",
                "--output",
                str(image_dir / "production-images.tar"),
                *images,
            ],
            cwd=staging,
        )
        return images
    finally:
        build_compose_file.unlink(missing_ok=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_file_manifest(staging: Path) -> None:
    manifest_path = staging / "SHA256SUMS.txt"
    lines = []
    for path in sorted(item for item in staging.rglob("*") if item.is_file()):
        if path == manifest_path:
            continue
        relative = path.relative_to(staging).as_posix()
        lines.append(f"{_sha256(path)}  {relative}")
    manifest_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _create_zip(staging: Path, destination: Path) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(item for item in staging.rglob("*") if item.is_file()):
            archive.write(path, Path(staging.name) / path.relative_to(staging))


def build_package(
    *,
    output_dir: Path,
    username: str,
    port: int,
    include_images: bool,
) -> dict[str, Any]:
    commit = _git_commit()
    release_version = f"{datetime.now(UTC):%Y%m%d}-{commit[:7]}"
    release_name = f"new-drug-intelligence-intranet-{release_version}"
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = output_dir / release_name
    archive = output_dir / f"{release_name}.zip"
    checksum = archive.with_suffix(".zip.sha256")
    for target in (staging, archive, checksum):
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()

    staging.mkdir()
    _copy_release_sources(staging)
    password = generate_env_safe_password()
    database_summary = prepare_release_database(
        SERVER_DIR / "data.db",
        staging / "seed" / "data.db",
        username=username,
        password=password,
    )
    storage_files = _copy_seed_storage(staging / "seed" / "storage")
    write_production_env(
        staging / ".env.production.initial",
        username=username,
        password=password,
        port=port,
        release_version=release_version,
    )
    (staging / "FIRST-LOGIN.txt").write_text(
        "\n".join(
            (
                "新药情报平台首次登录凭据",
                "",
                f"地址：http://<服务器IP>:{port}/",
                f"用户名：{username}",
                f"密码：{password}",
                "",
                "首次登录后请立即在账户面板修改密码，然后安全删除本文件。",
                "如果这是覆盖升级，系统会保留原 runtime 数据库，应继续使用原密码。",
                "",
            )
        ),
        encoding="utf-8",
    )

    images: list[str] = []
    if include_images:
        images = _build_offline_images(staging, release_version)
    version = {
        "product": "新药情报平台",
        "release_version": release_version,
        "git_commit": commit,
        "built_at": datetime.now(UTC).isoformat(),
        "intranet_port": port,
        "offline_images_included": include_images,
        "images": images,
        "database": database_summary,
        "snapshot_and_template_files": storage_files,
    }
    (staging / "VERSION.json").write_text(
        json.dumps(version, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_file_manifest(staging)
    _create_zip(staging, archive)
    checksum.write_text(f"{_sha256(archive)}  {archive.name}\n", encoding="utf-8")
    return {
        "release_directory": str(staging.resolve()),
        "archive": str(archive.resolve()),
        "archive_sha256": _sha256(archive),
        "checksum_file": str(checksum.resolve()),
        "release_version": release_version,
        "offline_images_included": include_images,
        "database": database_summary,
        "snapshot_and_template_files": storage_files,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a directly deployable intranet release bundle.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "artifacts" / "intranet-package",
    )
    parser.add_argument("--username", default="admin")
    parser.add_argument("--port", type=int, default=8093)
    parser.add_argument("--skip-images", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        raise ValueError("port must be between 1 and 65535")
    result = build_package(
        output_dir=args.output_dir,
        username=args.username,
        port=args.port,
        include_images=not args.skip_images,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
