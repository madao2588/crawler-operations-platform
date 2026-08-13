from datetime import datetime

from pydantic import BaseModel, Field, field_serializer

from app.schemas.serialization import dt_to_utc_iso_z


class NoticeSourceSiteOption(BaseModel):
    source_site: str
    display_name: str


class NoticeMonthOption(BaseModel):
    month: str = Field(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    count: int = Field(..., ge=0)


class NoticeListItem(BaseModel):
    id: int
    title: str = ""
    summary: str = ""
    source_site: str
    source_url: str = Field(..., min_length=1, max_length=2048)
    published_at: datetime | None = None
    captured_at: datetime
    quality_score: int = Field(..., ge=0, le=100)
    matched_keywords: list[str] = []
    is_high_priority: bool = False
    project_signal: str = "其他项目线索"
    category: str = "未分类"
    ai_summary: str | None = None
    review_status: str = "待关注"
    is_archived: bool = False
    is_focused: bool = False
    remark: str | None = None
    task_id: int

    @field_serializer("published_at", "captured_at", when_used="json")
    def _serialize_notice_times_utc_z(self, value: datetime | None) -> str | None:
        return dt_to_utc_iso_z(value)


class NoticeRead(NoticeListItem):
    content_text: str = ""
    content_html: str = ""
    content_hash: str | None = None
    snapshot_path: str | None = None
    metadata: dict[str, object] | None = None


class NoticeSnapshotRead(BaseModel):
    id: int
    source_url: str
    source_site: str
    snapshot_path: str
    content: str
