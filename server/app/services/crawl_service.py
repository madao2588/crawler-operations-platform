import asyncio
import logging
import traceback
from datetime import datetime, timedelta, timezone
from importlib import import_module

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.repositories.log_repo import LogRepository
from app.repositories.task_repo import TaskRepository
from app.schemas.task import TaskRunPayload

_background_tasks = set()


class TaskRunConflictError(RuntimeError):
    """Raised when a manual run is requested while the task is already queued or running."""


class CrawlService:
    def __init__(self, task_repo: TaskRepository, log_repo: LogRepository):
        self.task_repo = task_repo
        self.log_repo = log_repo
        settings = get_settings()
        self._task_stale_after = timedelta(minutes=max(settings.task_stale_minutes, 1))

    def _as_utc(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    async def recover_stale_tasks(self) -> list[int]:
        stale_before = datetime.now(timezone.utc) - self._task_stale_after
        stale_tasks = await self.task_repo.list_stale_active(stale_before=stale_before)
        recovered: list[int] = []
        for task in stale_tasks:
            stale_status = (task.last_run_status or "").strip() or "active"
            await self.task_repo.update_run_state(
                task,
                last_run_status="failed",
                last_error_message=(
                    "Recovered stale queued/running task after timeout; "
                    "previous execution was assumed lost."
                ),
            )
            await self.log_repo.create(
                level="WARNING",
                task_id=task.id,
                message=f"Task {task.id} recovered from stale {stale_status} state",
            )
            recovered.append(task.id)
        return recovered

    async def _recover_task_if_stale(self, task_id: int, *, now: datetime) -> bool:
        stale_before = now - self._task_stale_after
        task = await self.task_repo.get_by_id(task_id)
        if task is None:
            return False
        status = (task.last_run_status or "").strip()
        if status not in ("queued", "running"):
            return False
        last_run_at = self._as_utc(task.last_run_at)
        if last_run_at is None or last_run_at > stale_before:
            return False

        await self.task_repo.update_run_state(
            task,
            last_run_status="failed",
            last_error_message=(
                "Recovered stale queued/running task after timeout; "
                "previous execution was assumed lost."
            ),
        )
        await self.log_repo.create(
            level="WARNING",
            task_id=task_id,
            message=f"Task {task_id} recovered from stale {status} state before requeue",
        )
        return True

    async def run_task(self, task_id: int) -> None:
        task = await self.task_repo.get_by_id(task_id)
        if task is None:
            await self.log_repo.create(
                level="ERROR",
                task_id=task_id,
                message=f"Task {task_id} not found for execution",
            )
            raise LookupError(f"Task {task_id} not found")

        run_at = datetime.now(timezone.utc)
        await self._recover_task_if_stale(task_id, now=run_at)
        claimed = await self.task_repo.try_mark_running(task_id, run_at=run_at)
        if not claimed:
            claimed = await self.task_repo.try_promote_queued_to_running(task_id, run_at=run_at)
        if not claimed:
            snap = await self.task_repo.get_by_id(task_id)
            st = (snap.last_run_status or "").strip() if snap else ""
            await self.log_repo.create(
                level="INFO",
                task_id=task_id,
                message=(
                    f"Task {task_id} execution skipped (status={st!r}; "
                    "already running or concurrent claim lost)"
                ),
            )
            return

        task = await self.task_repo.get_by_id(task_id)
        if task is None:
            await self.log_repo.create(
                level="ERROR",
                task_id=task_id,
                message=f"Task {task_id} disappeared after run claim",
            )
            raise LookupError(f"Task {task_id} not found")

        pipeline_module = import_module("app.engine.pipeline")
        pipeline_runner = getattr(pipeline_module, "run_task", None)
        if not callable(pipeline_runner):
            await self.task_repo.update_run_state(
                task,
                last_run_status="idle",
                last_error_message="Pipeline runner is not implemented yet",
            )
            await self.log_repo.create(
                level="WARNING",
                task_id=task_id,
                message="Pipeline runner is not implemented yet",
            )
            return

        try:
            pipeline_result = await pipeline_runner(task_id)
            completed_status = "partial" if pipeline_result == "partial" else "success"
            completion_error = (
                "Run completed with partial failures; inspect the latest run summary."
                if completed_status == "partial"
                else None
            )
            refreshed_task = await self.task_repo.get_by_id(task_id)
            if refreshed_task is not None:
                await self.task_repo.update_run_state(
                    refreshed_task,
                    last_run_status=completed_status,
                    last_success_at=datetime.now(timezone.utc),
                    last_error_message=completion_error,
                )
            await self.log_repo.create(
                level="WARNING" if completed_status == "partial" else "INFO",
                task_id=task_id,
                message=f"Task {task_id} execution finished with status={completed_status}",
            )
        except Exception as exc:
            failed_task = await self.task_repo.get_by_id(task_id)
            if failed_task is not None:
                await self.task_repo.update_run_state(
                    failed_task,
                    last_run_status="failed",
                    last_error_message=str(exc),
                )
            await self.log_repo.create(
                level="ERROR",
                task_id=task_id,
                message=f"Task {task_id} execution failed",
                error_stack=str(exc),
            )
            raise

    async def trigger_now(self, task_id: int) -> TaskRunPayload:
        task = await self.task_repo.get_by_id(task_id)
        if task is None:
            raise LookupError(f"Task {task_id} not found")

        now = datetime.now(timezone.utc)
        recovered_stale_run = await self._recover_task_if_stale(task_id, now=now)
        if not await self.task_repo.try_mark_run_queued(task_id, run_at=now):
            raise TaskRunConflictError(f"Task {task_id} is already running or queued; wait for completion.")

        task_coro = asyncio.create_task(dispatch_task_run(task_id))
        _background_tasks.add(task_coro)
        task_coro.add_done_callback(_background_tasks.discard)
        return TaskRunPayload(
            task_id=task_id,
            status="queued",
            recovered_stale_run=recovered_stale_run,
        )

    async def collect_manual_url(self, task_id: int, url: str) -> dict[str, object]:
        task = await self.task_repo.get_by_id(task_id)
        if task is None:
            raise LookupError(f"Task {task_id} not found")

        pipeline_module = import_module("app.engine.pipeline")
        collector = getattr(pipeline_module, "collect_manual_url", None)
        if not callable(collector):
            raise RuntimeError("Manual collection runner is not implemented")

        from app.repositories.data_repo import DataRepository

        return await collector(
            task_id=task.id,
            url=url,
            parser_rules=task.parser_rules,
            log_repo=self.log_repo,
            data_repo=DataRepository(self.task_repo.session),
        )


async def _mark_task_failed_after_dispatch_crash(task_id: int, exc: BaseException) -> None:
    """If the background runner dies, unblock queued/running tasks and persist the error."""
    msg = f"{type(exc).__name__}: {exc}"[:2000]
    stack = traceback.format_exc()
    async with AsyncSessionLocal() as session:
        task_repo = TaskRepository(session)
        log_repo = LogRepository(session)
        row = await task_repo.get_by_id(task_id)
        if row is None:
            return
        st = (row.last_run_status or "").strip()
        if st in ("queued", "running"):
            await task_repo.update_run_state(
                row,
                last_run_status="failed",
                last_error_message=msg,
            )
            await log_repo.create(
                level="ERROR",
                task_id=task_id,
                message=f"Task {task_id} background run crashed before completion",
                error_stack=stack,
            )


async def dispatch_task_run(task_id: int) -> None:
    try:
        async with AsyncSessionLocal() as session:
            task_repo = TaskRepository(session)
            log_repo = LogRepository(session)
            service = CrawlService(task_repo=task_repo, log_repo=log_repo)
            await service.run_task(task_id)
    except BaseException as exc:
        if isinstance(exc, asyncio.CancelledError):
            raise
        logging.exception("dispatch_task_run(%s) crashed", task_id)
        await _mark_task_failed_after_dispatch_crash(task_id, exc)
