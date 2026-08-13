from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import sqlite3

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, resolve_database_path, server_dir
from app.repositories.auth_repo import AuthRepository
from app.repositories.log_repo import LogRepository


@dataclass(slots=True)
class MaintenanceResult:
    backup_path: str | None
    deleted_expired_sessions: int
    deleted_old_logs: int
    deleted_old_exports: int
    deleted_old_manifests: int
    deleted_old_backups: int


class MaintenanceService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.database_path = resolve_database_path()
        self.backups_dir = (server_dir / self.settings.maintenance_backup_dir).resolve()
        self.exports_dir = (server_dir / self.settings.export_dir).resolve()
        self.snapshots_dir = (server_dir / self.settings.snapshot_dir).resolve()

    async def run_startup_maintenance(self) -> MaintenanceResult:
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        backup_path = self._backup_database()
        deleted_old_exports = self._cleanup_exports()
        deleted_old_manifests = self._cleanup_snapshot_manifests()
        deleted_old_backups = self._cleanup_backups()

        async with AsyncSessionLocal() as session:
            auth_repo = AuthRepository(session)
            log_repo = LogRepository(session)
            deleted_expired_sessions = await auth_repo.delete_expired_sessions(
                expired_before=datetime.now(UTC),
            )
            deleted_old_logs = await log_repo.delete_older_than(
                older_than=datetime.now(UTC) - timedelta(days=self.settings.maintenance_log_retention_days),
            )

        return MaintenanceResult(
            backup_path=str(backup_path) if backup_path else None,
            deleted_expired_sessions=deleted_expired_sessions,
            deleted_old_logs=deleted_old_logs,
            deleted_old_exports=deleted_old_exports,
            deleted_old_manifests=deleted_old_manifests,
            deleted_old_backups=deleted_old_backups,
        )

    def _backup_database(self) -> Path:
        timestamp = datetime.now(UTC).astimezone().strftime("%Y%m%d-%H%M%S")
        backup_path = self.backups_dir / f"data.{timestamp}.db"
        with sqlite3.connect(f"file:{self.database_path.resolve()}?mode=ro", uri=True) as source:
            with sqlite3.connect(backup_path) as target:
                source.backup(target)
                integrity = target.execute("PRAGMA integrity_check").fetchone()
                if integrity is None or integrity[0] != "ok":
                    raise RuntimeError(f"maintenance backup integrity check failed: {integrity}")
        manifest = {
            "generated_at": datetime.now(UTC).isoformat(),
            "database_path": str(self.database_path),
            "backup_path": str(backup_path),
            "snapshot_dir": str(self.snapshots_dir),
            "export_dir": str(self.exports_dir),
        }
        (backup_path.with_suffix(".json")).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return backup_path

    def _cleanup_exports(self) -> int:
        return self._delete_files_older_than(
            self.exports_dir,
            suffixes=None,
            older_than_days=self.settings.maintenance_export_retention_days,
        )

    def _cleanup_snapshot_manifests(self) -> int:
        return self._delete_files_older_than(
            self.snapshots_dir,
            suffixes={".json", ".manifest", ".txt"},
            older_than_days=self.settings.maintenance_manifest_retention_days,
        )

    def _cleanup_backups(self) -> int:
        return self._delete_files_older_than(
            self.backups_dir,
            suffixes={".db", ".json"},
            older_than_days=self.settings.maintenance_backup_retention_days,
        )

    def _delete_files_older_than(
        self,
        directory: Path,
        *,
        suffixes: set[str] | None,
        older_than_days: int,
    ) -> int:
        if not directory.exists():
            return 0
        cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
        deleted = 0
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            if path.name == ".gitkeep":
                continue
            if suffixes is not None and path.suffix.lower() not in suffixes:
                continue
            modified_at = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
            if modified_at >= cutoff:
                continue
            path.unlink(missing_ok=True)
            deleted += 1
        return deleted
