from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.notice import NoticeListItem


class KeywordHeatItem(BaseModel):
    keyword: str
    count: int = Field(..., ge=0)


class SourceDistributionItem(BaseModel):
    source_site: str
    display_name: str
    notice_count: int = Field(..., ge=0)
    percentage: float = Field(..., ge=0, le=100)


class ProjectSignalItem(BaseModel):
    label: str
    notice_count: int = Field(..., ge=0)
    percentage: float = Field(..., ge=0, le=100)


class DashboardMetrics(BaseModel):
    today_new_notices: int = Field(..., ge=0)
    keyword_hit_notices: int = Field(..., ge=0)
    monitoring_site_count: int = Field(..., ge=0)
    high_priority_notices: int = Field(..., ge=0)
    high_quality_notices: int = Field(default=0, ge=0)
    project_declaration_notices: int = Field(default=0, ge=0)
    result_publication_notices: int = Field(default=0, ge=0)


class DashboardRuntime(BaseModel):
    """与 /health 一致的本地运行态，便于控制台首页自检。"""

    status: str
    database: str
    scheduler: str
    scheduled_jobs: int = Field(default=0, ge=0)


class DashboardCollectionIssue(BaseModel):
    task_id: int
    task_name: str
    status: str
    reason: str
    failure_kind: str | None = None
    backoff_active: bool = False
    next_retry_at: datetime | None = None
    is_stale: bool = False
    last_success_at: datetime | None = None


class DashboardCollectionHealth(BaseModel):
    status: str
    monitored_task_count: int = Field(default=0, ge=0)
    failed_task_count: int = Field(default=0, ge=0)
    partial_task_count: int = Field(default=0, ge=0)
    stale_task_count: int = Field(default=0, ge=0)
    backoff_task_count: int = Field(default=0, ge=0)
    last_success_at: datetime | None = None
    failed_sources: list[str] = Field(default_factory=list)
    partial_sources: list[str] = Field(default_factory=list)
    issues: list[DashboardCollectionIssue] = Field(default_factory=list)


class DashboardOverview(BaseModel):
    metrics: DashboardMetrics
    runtime: DashboardRuntime
    collection_health: DashboardCollectionHealth
    high_value_notices: list[NoticeListItem]
    recent_notices: list[NoticeListItem]
    keyword_heat: list[KeywordHeatItem]
    source_distribution: list[SourceDistributionItem]
    project_signal_distribution: list[ProjectSignalItem] = []
    last_updated_at: datetime | None = None
