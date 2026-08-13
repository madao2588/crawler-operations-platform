import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.scheduler import get_scheduler
from app.models.task import Task
from app.repositories.log_repo import LogRepository
from app.repositories.task_repo import TaskRepository
from app.schemas.common import EmptyPayload, PageData
from app.schemas.task import (
    DeferredTaskPayload,
    RunAllEnabledPayload,
    TaskCreate,
    TaskRead,
    TaskRunPayload,
    TaskStatus,
    TaskUpdate,
)
from app.schemas.template import ManualCollectionRead
from app.services.crawl_service import CrawlService, TaskRunConflictError, dispatch_task_run
from app.services.template_service import NEW_DRUG_SOURCE_TEMPLATES
from app.utils.url_security import UnsafeTargetError, assert_safe_outbound_url, normalize_allowed_hosts
from app.utils.task_retry import is_retry_backoff_active


DEMO_TASK_START_URLS = frozenset(
    {
        "https://example.com",
        "https://movie.douban.com/top250",
        "https://www.xiaohongshu.com/explore",
        "https://store.steampowered.com/search/?filter=topsellers",
        "https://www.v2ex.com/?tab=hot",
    }
)


class TaskBusyError(RuntimeError):
    """Raised when deleting or mutating a task that is still running or queued."""


class TaskService:
    def __init__(
        self,
        task_repo: TaskRepository,
        log_repo: LogRepository,
        crawl_service: CrawlService,
        scheduler: AsyncIOScheduler | None = None,
    ):
        self.task_repo = task_repo
        self.log_repo = log_repo
        self.crawl_service = crawl_service
        self.scheduler = scheduler or get_scheduler()

    async def list_tasks(
        self,
        *,
        page: int,
        page_size: int,
        search: str | None = None,
        enabled: str | None = None,
        last_run: str | None = None,
        sort_by: str | None = None,
        sort_dir: str | None = None,
    ) -> PageData[TaskRead]:
        needle = (search or "").strip()
        if len(needle) > 200:
            needle = needle[:200]
        items, total = await self.task_repo.list_paginated(
            page=page,
            page_size=page_size,
            search=needle or None,
            enabled=enabled,
            last_run=last_run,
            sort_by=sort_by,
            sort_dir=sort_dir,
        )
        return PageData[TaskRead](
            items=[TaskRead.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_task(self, task_id: int) -> TaskRead:
        task = await self._get_task_or_raise(task_id)
        return TaskRead.model_validate(task)

    async def create_task(self, payload: TaskCreate) -> TaskRead:
        self._validate_cron_expr(payload.cron_expr)
        task = await self.task_repo.create(payload)
        await self._sync_scheduler(task)
        await self.log_repo.create(
            level="INFO",
            task_id=task.id,
            message=f"Task {task.id} created",
        )
        return TaskRead.model_validate(task)

    async def update_task(self, task_id: int, payload: TaskUpdate) -> TaskRead:
        task = await self._get_task_or_raise(task_id)
        update_data = payload.model_dump(exclude_unset=True)
        cron_expr = update_data.get("cron_expr")
        if cron_expr is not None:
            self._validate_cron_expr(cron_expr)

        updated_task = await self.task_repo.update(task, payload)
        await self._sync_scheduler(updated_task)
        await self.log_repo.create(
            level="INFO",
            task_id=updated_task.id,
            message=f"Task {updated_task.id} updated",
        )
        return TaskRead.model_validate(updated_task)

    async def delete_task(self, task_id: int) -> EmptyPayload:
        task = await self._get_task_or_raise(task_id)
        if task.last_run_status in ("running", "queued"):
            raise TaskBusyError(f"Task {task_id} is {task.last_run_status}; wait for completion or try again later.")
        self._remove_job(task.id)
        await self.task_repo.delete(task)
        await self.log_repo.create(
            level="INFO",
            task_id=None,
            message=f"Task {task_id} deleted",
        )
        return EmptyPayload()

    async def run_task_now(self, task_id: int) -> TaskRunPayload:
        await self._get_task_or_raise(task_id)
        return await self.crawl_service.trigger_now(task_id)

    async def collect_manual_source(
        self,
        source_id: str,
        url: str,
    ) -> ManualCollectionRead:
        source = next(
            (
                item
                for item in NEW_DRUG_SOURCE_TEMPLATES
                if str(item["id"]) == source_id
            ),
            None,
        )
        rules = json.loads(source["parser_rules"]) if source and source.get("parser_rules") else {}
        if rules.get("collection_mode") != "manual":
            raise ValueError(f"Source {source_id} does not support manual collection")

        parsed_url = urlparse(url.strip())
        allowed_hosts = normalize_allowed_hosts(
            host for host in rules.get("allowed_hosts", []) if isinstance(host, str)
        )
        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.hostname
            or parsed_url.hostname.lower().rstrip(".") not in allowed_hosts
        ):
            allowed = ", ".join(sorted(allowed_hosts)) or "configured source host"
            raise ValueError(f"Manual source URL must use {allowed}")
        try:
            safe_url = assert_safe_outbound_url(url.strip())
        except UnsafeTargetError as exc:
            raise ValueError(str(exc)) from exc

        task = await self.task_repo.get_by_name(str(source["name"]))
        if task is None:
            raise LookupError(f"Task for source {source_id} not found")

        result = await self.crawl_service.collect_manual_url(task.id, safe_url)
        return ManualCollectionRead(source_id=source_id, **result)

    async def run_all_enabled_tasks_now(self) -> RunAllEnabledPayload:
        enabled_tasks = await self.task_repo.list_enabled()
        queued: list[int] = []
        skipped: list[int] = []
        recovered: list[int] = []
        deferred: list[DeferredTaskPayload] = []
        errors: list[str] = []
        current = datetime.now(timezone.utc)
        for task in enabled_tasks:
            backoff_active, failure_kind, next_retry_at = is_retry_backoff_active(
                now=current,
                last_run_status=getattr(task, "last_run_status", None),
                last_run_at=getattr(task, "last_run_at", None),
                last_error_message=getattr(task, "last_error_message", None),
            )
            if backoff_active and failure_kind and next_retry_at is not None:
                deferred.append(
                    DeferredTaskPayload(
                        task_id=task.id,
                        task_name=task.name,
                        failure_kind=failure_kind,
                        next_retry_at=next_retry_at,
                        retry_in_seconds=max(0, int((next_retry_at - current).total_seconds())),
                    )
                )
                continue
            try:
                result = await self.crawl_service.trigger_now(task.id)
                queued.append(task.id)
                if result.recovered_stale_run:
                    recovered.append(task.id)
            except TaskRunConflictError:
                skipped.append(task.id)
            except LookupError:
                errors.append(f"task {task.id} not found")
        await self.log_repo.create(
            level="INFO",
            task_id=None,
            message=(
                "bulk run-enabled: "
                f"queued={len(queued)} skipped={len(skipped)} "
                f"recovered={len(recovered)} deferred={len(deferred)} errors={len(errors)}"
            ),
        )
        return RunAllEnabledPayload(
            queued_task_ids=queued,
            skipped_task_ids=skipped,
            recovered_task_ids=recovered,
            quarantined_task_ids=[],
            deferred_tasks=deferred,
            errors=errors,
        )

    async def load_enabled_tasks(self) -> None:
        enabled_tasks = await self.task_repo.list_enabled()
        for task in enabled_tasks:
            try:
                await self._sync_scheduler(task)
            except ValueError as exc:
                await self.log_repo.create(
                    level="ERROR",
                    task_id=task.id,
                    message=f"Failed to load scheduled task {task.id}",
                    error_stack=str(exc),
                )

    async def catch_up_stale_tasks(
        self,
        *,
        now: datetime | None = None,
        stale_after: timedelta = timedelta(hours=24),
    ) -> RunAllEnabledPayload:
        current = now or datetime.now(timezone.utc)
        stale_tasks = await self.task_repo.list_stale_enabled(
            stale_before=current - stale_after,
        )
        queued: list[int] = []
        skipped: list[int] = []
        deferred: list[DeferredTaskPayload] = []
        errors: list[str] = []
        for task in stale_tasks:
            backoff_active, failure_kind, next_retry_at = is_retry_backoff_active(
                now=current,
                last_run_status=getattr(task, "last_run_status", None),
                last_run_at=getattr(task, "last_run_at", None),
                last_error_message=getattr(task, "last_error_message", None),
            )
            if backoff_active and failure_kind and next_retry_at is not None:
                deferred.append(
                    DeferredTaskPayload(
                        task_id=task.id,
                        task_name=task.name,
                        failure_kind=failure_kind,
                        next_retry_at=next_retry_at,
                        retry_in_seconds=max(0, int((next_retry_at - current).total_seconds())),
                    )
                )
                continue
            try:
                await self.crawl_service.trigger_now(task.id)
                queued.append(task.id)
            except TaskRunConflictError:
                skipped.append(task.id)
            except (LookupError, RuntimeError) as exc:
                errors.append(f"task {task.id}: {exc}")

        await self.log_repo.create(
            level="WARNING" if errors else "INFO",
            task_id=None,
            message=(
                "startup catch-up: "
                f"queued={len(queued)} skipped={len(skipped)} "
                f"deferred={len(deferred)} errors={len(errors)}"
            ),
            error_stack="\n".join(errors) if errors else None,
        )
        return RunAllEnabledPayload(
            queued_task_ids=queued,
            skipped_task_ids=skipped,
            recovered_task_ids=[],
            quarantined_task_ids=[],
            deferred_tasks=deferred,
            errors=errors,
        )

    async def ensure_example_task(self) -> TaskRead | None:
        if await self.task_repo.count_all() > 0:
            return None

        example = TaskCreate(
            name="Example News Task",
            start_url="https://example.com",
            parser_rules=None,
            cron_expr="0 */6 * * *",
            status=TaskStatus.ENABLED,
        )
        return await self.create_task(example)

    async def ensure_required_source_tasks(self) -> None:
        deleted_count = await self.task_repo.delete_by_start_urls(DEMO_TASK_START_URLS)
        if deleted_count:
            await self.log_repo.create(
                level="INFO",
                task_id=None,
                message=f"Removed {deleted_count} demo tasks before seeding required source tasks",
            )

        existing_tasks = await self.task_repo.list_all()
        existing_by_name = {task.name: task for task in existing_tasks}
        existing_by_start_url: dict[str, list[Task]] = {}
        for task in existing_tasks:
            existing_by_start_url.setdefault(task.start_url, []).append(task)
        canonical_url_counts: dict[str, int] = {}
        for source in NEW_DRUG_SOURCE_TEMPLATES:
            start_url = str(source["start_url"])
            canonical_url_counts[start_url] = canonical_url_counts.get(start_url, 0) + 1

        for source in NEW_DRUG_SOURCE_TEMPLATES:
            name = str(source["name"])
            start_url = str(source["start_url"])
            existing = existing_by_name.get(name)
            if existing is None and canonical_url_counts[start_url] == 1:
                same_url = existing_by_start_url.get(start_url, [])
                if len(same_url) == 1:
                    existing = same_url[0]
            if existing is not None:
                update = TaskUpdate(
                    name=name,
                    start_url=start_url,
                    parser_rules=source["parser_rules"],
                    cron_expr=str(source["cron_expr"]),
                    status=TaskStatus.ENABLED if source["enabled"] else TaskStatus.DISABLED,
                )
                await self.update_task(existing.id, update)
                continue

            created = await self.create_task(
                TaskCreate(
                    name=name,
                    start_url=start_url,
                    parser_rules=source["parser_rules"],
                    cron_expr=str(source["cron_expr"]),
                    status=TaskStatus.ENABLED if source["enabled"] else TaskStatus.DISABLED,
                )
            )
            existing_by_name[created.name] = await self.task_repo.get_by_id(created.id) or existing
            created_task = existing_by_name[created.name]
            if created_task is not None:
                existing_by_start_url.setdefault(start_url, []).append(created_task)

    async def _sync_scheduler(self, task: Task) -> None:
        if int(task.status) != int(TaskStatus.ENABLED):
            self._remove_job(task.id)
            return

        trigger = CronTrigger.from_crontab(task.cron_expr)
        self.scheduler.add_job(
            dispatch_task_run,
            trigger=trigger,
            args=[task.id],
            id=self._job_id(task.id),
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=3600,
        )

    async def _get_task_or_raise(self, task_id: int) -> Task:
        task = await self.task_repo.get_by_id(task_id)
        if task is None:
            raise LookupError(f"Task {task_id} not found")
        return task

    def _validate_cron_expr(self, cron_expr: str) -> None:
        CronTrigger.from_crontab(cron_expr)

    def _remove_job(self, task_id: int) -> None:
        try:
            self.scheduler.remove_job(self._job_id(task_id))
        except JobLookupError:
            return

    def _job_id(self, task_id: int) -> str:
        return f"task_{task_id}"
