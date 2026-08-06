from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.repositories.auth_repo import AuthRepository
from app.repositories.data_repo import DataRepository
from app.repositories.log_repo import LogRepository
from app.repositories.keyword_rule_repo import KeywordRepository
from app.repositories.task_repo import TaskRepository
from app.repositories.template_repo import TemplateRepository
from app.schemas.auth import AuthSessionRead
from app.services.auth_service import AuthService
from app.services.crawl_service import CrawlService
from app.services.dashboard_service import DashboardService
from app.services.data_service import DataService
from app.services.notice_service import NoticeService
from app.services.task_service import TaskService
from app.services.template_service import TemplateService


def get_task_repository(session: AsyncSession = Depends(get_db_session)) -> TaskRepository:
    return TaskRepository(session)


def get_auth_repository(session: AsyncSession = Depends(get_db_session)) -> AuthRepository:
    return AuthRepository(session)


def get_data_repository(session: AsyncSession = Depends(get_db_session)) -> DataRepository:
    return DataRepository(session)


def get_log_repository(session: AsyncSession = Depends(get_db_session)) -> LogRepository:
    return LogRepository(session)


def get_keyword_rule_repository(session: AsyncSession = Depends(get_db_session)) -> KeywordRepository:
    return KeywordRepository(session)


def get_template_repository(session: AsyncSession = Depends(get_db_session)) -> TemplateRepository:
    return TemplateRepository(session)


def get_crawl_service(
    task_repo: TaskRepository = Depends(get_task_repository),
    log_repo: LogRepository = Depends(get_log_repository),
) -> CrawlService:
    return CrawlService(task_repo=task_repo, log_repo=log_repo)


def get_task_service(
    task_repo: TaskRepository = Depends(get_task_repository),
    log_repo: LogRepository = Depends(get_log_repository),
    crawl_service: CrawlService = Depends(get_crawl_service),
) -> TaskService:
    return TaskService(
        task_repo=task_repo,
        log_repo=log_repo,
        crawl_service=crawl_service,
    )


def get_data_service(
    data_repo: DataRepository = Depends(get_data_repository),
    task_repo: TaskRepository = Depends(get_task_repository),
    log_repo: LogRepository = Depends(get_log_repository),
) -> DataService:
    return DataService(
        data_repo=data_repo,
        task_repo=task_repo,
        log_repo=log_repo,
    )


def get_notice_service(
    data_repo: DataRepository = Depends(get_data_repository),
    keyword_repo: KeywordRepository = Depends(get_keyword_rule_repository),
) -> NoticeService:
    return NoticeService(data_repo=data_repo, keyword_repo=keyword_repo)


def get_dashboard_service(
    data_repo: DataRepository = Depends(get_data_repository),
    task_repo: TaskRepository = Depends(get_task_repository),
    keyword_repo: KeywordRepository = Depends(get_keyword_rule_repository),
) -> DashboardService:
    return DashboardService(
        data_repo=data_repo,
        task_repo=task_repo,
        keyword_repo=keyword_repo,
    )


def get_template_service(
    template_repo: TemplateRepository = Depends(get_template_repository),
) -> TemplateService:
    return TemplateService(template_repo=template_repo)


def get_auth_service(
    auth_repo: AuthRepository = Depends(get_auth_repository),
) -> AuthService:
    return AuthService(auth_repo=auth_repo)


def get_bearer_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token format",
        )

    return token.strip()


async def get_current_session(
    token: str = Depends(get_bearer_token),
    service: AuthService = Depends(get_auth_service),
) -> AuthSessionRead:
    try:
        return await service.get_session(token)
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


async def require_admin(
    session_data: AuthSessionRead = Depends(get_current_session),
) -> AuthSessionRead:
    if session_data.user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅管理员可执行此操作",
        )
    return session_data
