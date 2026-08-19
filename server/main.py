import asyncio
import sys
import os

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import auth, dashboard, data, keyword_rule, logs, notice, stats, task, template
from app.core.exceptions import (
    fastapi_http_exception_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.lifecycle import lifespan
from app.core.config import get_settings
from app.core.runtime_status import get_runtime_snapshot
from app.schemas.common import ApiResponse, HealthPayload

settings = get_settings()


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins_list,
        allow_origin_regex=settings.cors_allowed_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(task.router, prefix=settings.api_prefix)
    app.include_router(data.router, prefix=settings.api_prefix)
    app.include_router(stats.router, prefix=settings.api_prefix)
    app.include_router(logs.router, prefix=settings.api_prefix)
    app.include_router(notice.router, prefix=settings.api_prefix)
    app.include_router(dashboard.router, prefix=settings.api_prefix)
    app.include_router(template.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(keyword_rule.router, prefix=settings.api_prefix)

    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(HTTPException, fastapi_http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    return app


app = create_app()

@app.get("/health", response_model=ApiResponse[HealthPayload])
async def root() -> ApiResponse[HealthPayload]:
    snap = await get_runtime_snapshot()
    return ApiResponse(
        data=HealthPayload(
            status=snap["status"],
            app_name=settings.app_name,
            release_version=settings.release_version,
            database=snap["database"],
            scheduler=snap["scheduler"],
            scheduled_jobs=snap["scheduled_jobs"],
        )
    )

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend", "build", "web")
if os.path.exists(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
