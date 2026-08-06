from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, Field, field_serializer

from app.schemas.serialization import dt_to_utc_iso_z


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 0
    message: str = "success"
    data: T | None = None


class HealthPayload(BaseModel):
    """本地/运维探活：整体状态 + 依赖子项，便于排查「调度是否在跑、库是否可连」。"""

    status: str
    app_name: str
    database: str = "unknown"
    scheduler: str = "unknown"
    scheduled_jobs: int = Field(default=0, ge=0)


class EmptyPayload(BaseModel):
    pass


class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class PageData(BaseModel, Generic[T]):
    items: list[T]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=100)


class RunSummaryPayload(BaseModel):
    run_id: str | None = None
    mode: str
    metrics: dict[str, str | int | bool]


class LogRead(BaseModel):
    id: int
    task_id: int | None = None
    level: str
    message: str
    error_stack: str | None = None
    run_summary: RunSummaryPayload | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at", when_used="json")
    def _serialize_created_at_utc_z(self, value: datetime) -> str:
        return dt_to_utc_iso_z(value) or ""


class LogSummary(BaseModel):
    total_logs: int = Field(..., ge=0)
    info_logs: int = Field(..., ge=0)
    warning_logs: int = Field(..., ge=0)
    error_logs: int = Field(..., ge=0)
    failed_task_count: int = Field(..., ge=0)


class StatsOverview(BaseModel):
    total_tasks: int = Field(..., ge=0)
    enabled_tasks: int = Field(..., ge=0)
    total_data: int = Field(..., ge=0)
    today_data: int = Field(..., ge=0)
    total_logs: int = Field(..., ge=0)
    avg_quality_score: float = Field(..., ge=0, le=100)
