import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.models_base import Base


_active_test_db_path: Path | None = None


@pytest.fixture(scope="session")
def asgi_test_client() -> TestClient:
    """Single ASGI lifespan for the whole suite (APScheduler binds one event loop)."""
    from main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def bootstrap_admin_credentials() -> tuple[str, str]:
    return (
        os.environ["CRAWLER_BOOTSTRAP_ADMIN_USERNAME"],
        os.environ["CRAWLER_BOOTSTRAP_ADMIN_PASSWORD"],
    )


@pytest.fixture(scope="session")
def test_database_path() -> Path:
    if _active_test_db_path is None:
        raise RuntimeError("test_database_path requires the isolated SQLite test database")
    return _active_test_db_path


@pytest.fixture
def auth_headers(
    asgi_test_client: TestClient,
    bootstrap_admin_credentials: tuple[str, str],
) -> dict[str, str]:
    username, password = bootstrap_admin_credentials
    login = asgi_test_client.post(
        "/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert login.status_code == 200
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def pytest_configure() -> None:
    """Give each pytest process its own DB so parallel or stale runs cannot collide."""
    global _active_test_db_path

    if not os.environ.get("CRAWLER_DATABASE_URL"):
        db_path = Path(__file__).resolve().parent.parent / f"_pytest_crawler_{os.getpid()}.db"
        _remove_sqlite_files(db_path)
        os.environ["CRAWLER_DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"
        _active_test_db_path = db_path
    os.environ.setdefault("CRAWLER_BOOTSTRAP_ADMIN_USERNAME", "pytest_admin")
    os.environ.setdefault("CRAWLER_BOOTSTRAP_ADMIN_PASSWORD", "pytest-password-123")
    from app.core.config import get_settings

    get_settings.cache_clear()


def pytest_unconfigure() -> None:
    if _active_test_db_path is not None:
        _remove_sqlite_files(_active_test_db_path)


def _remove_sqlite_files(db_path: Path) -> None:
    for suffix in ("", "-shm", "-wal"):
        candidate = Path(f"{db_path}{suffix}")
        try:
            candidate.unlink(missing_ok=True)
        except PermissionError:
            # A crashed child may briefly retain a Windows handle. The next run
            # uses another PID-specific filename, so leaving this artifact is safe.
            continue


def _import_models() -> None:
    from app.models.auth import User, UserSession  # noqa: F401
    from app.models.data import CollectedData  # noqa: F401
    from app.models.keyword_rule import KeywordRule  # noqa: F401
    from app.models.log import LogEntry  # noqa: F401
    from app.models.task import Task  # noqa: F401
    from app.models.template import TaskTemplate  # noqa: F401


@pytest.fixture
async def async_session() -> AsyncSession:
    _import_models()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    await engine.dispose()
