from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal, close_db, init_db
from app.core.scheduler import get_scheduler
from app.repositories.auth_repo import AuthRepository
from app.repositories.log_repo import LogRepository
from app.repositories.keyword_rule_repo import KeywordRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.template_repo import TemplateRepository
from app.services.auth_service import AuthService
from app.services.crawl_service import CrawlService
from app.services.keyword_rule_service import KeywordService
from app.services.maintenance_service import MaintenanceService
from app.services.task_service import TaskService
from app.services.template_service import TemplateService


settings = get_settings()
server_dir = Path(__file__).resolve().parents[2]


def ensure_runtime_directories() -> None:
    for relative_path in (
        settings.snapshot_dir,
        settings.export_dir,
        settings.maintenance_backup_dir,
    ):
        (server_dir / relative_path).mkdir(parents=True, exist_ok=True)


async def run_startup_maintenance() -> None:
    if not settings.maintenance_enabled:
        return
    maintenance = MaintenanceService()
    await maintenance.run_startup_maintenance()


def schedule_daily_maintenance(scheduler) -> None:  # noqa: ANN001
    if not settings.maintenance_enabled:
        return
    scheduler.add_job(
        run_startup_maintenance,
        "cron",
        hour=3,
        minute=30,
        timezone="Asia/Shanghai",
        id="daily-maintenance",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
    )


async def bootstrap_tasks() -> None:
    async with AsyncSessionLocal() as session:
        task_repo = TaskRepository(session)
        log_repo = LogRepository(session)
        crawl_service = CrawlService(task_repo=task_repo, log_repo=log_repo)
        task_service = TaskService(
            task_repo=task_repo,
            log_repo=log_repo,
            crawl_service=crawl_service,
        )
        await task_service.ensure_required_source_tasks()
        await crawl_service.recover_stale_tasks()
        await task_service.load_enabled_tasks()
        if settings.startup_catch_up_enabled:
            await task_service.catch_up_stale_tasks()


async def bootstrap_auth() -> None:
    async with AsyncSessionLocal() as session:
        auth_repo = AuthRepository(session)
        auth_service = AuthService(auth_repo=auth_repo)
        await auth_service.ensure_default_admin()


async def bootstrap_templates() -> None:
    async with AsyncSessionLocal() as session:
        template_repo = TemplateRepository(session)
        template_service = TemplateService(template_repo=template_repo)
        await template_service.ensure_seed_data()


async def bootstrap_keywords() -> None:
    async with AsyncSessionLocal() as session:
        keyword_repo = KeywordRepository(session)
        keyword_service = KeywordService(keyword_repo)
        await keyword_service.ensure_seed_data()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    ensure_runtime_directories()
    await init_db()
    await run_startup_maintenance()
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
    schedule_daily_maintenance(scheduler)
    await bootstrap_auth()
    await bootstrap_keywords()
    await bootstrap_templates()
    await bootstrap_tasks()
    try:
        yield
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)
        await close_db()
