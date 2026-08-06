from datetime import datetime

from pydantic import BaseModel, Field, field_serializer

from app.schemas.serialization import dt_to_utc_iso_z


class DataRead(BaseModel):
    id: int
    task_id: int
    title: str | None = None
    content_html: str | None = None
    content_text: str | None = None
    source_url: str = Field(..., min_length=1, max_length=2048)
    snapshot_path: str | None = None
    quality_score: int = Field(..., ge=0, le=100)
    content_hash: str | None = None
    category: str = "未分类"
    ai_summary: str | None = None
    metadata_json: str | None = None
    review_status: str = "待关注"
    is_archived: bool = False
    remark: str | None = None
    published_at: datetime | None = None
    fetch_time: datetime

    model_config = {"from_attributes": True}

    @field_serializer("published_at", "fetch_time", when_used="json")
    def _serialize_times_utc_z(self, value: datetime | None) -> str | None:
        return dt_to_utc_iso_z(value)


class DataListItem(DataRead):
    pass


class DataReviewUpdate(BaseModel):
    category: str | None = Field(default=None, min_length=1, max_length=100)
    review_status: str | None = Field(default=None, min_length=1, max_length=20)
    is_archived: bool | None = None
    remark: str | None = Field(default=None, max_length=2000)


class SnapshotRead(BaseModel):
    id: int
    snapshot_path: str
    content: str
