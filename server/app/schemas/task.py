from datetime import datetime
from enum import IntEnum

from pydantic import BaseModel, Field, field_serializer, field_validator

from app.schemas.serialization import dt_to_utc_iso_z

from app.schemas.parser_rules import validate_parser_rules_str


class TaskStatus(IntEnum):
    DISABLED = 0
    ENABLED = 1


class TaskBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    start_url: str = Field(..., min_length=1, max_length=2048)
    parser_rules: str | None = Field(default=None, max_length=131072)
    cron_expr: str = Field(..., min_length=1, max_length=100)
    status: TaskStatus = TaskStatus.ENABLED

    @field_validator("start_url")
    @classmethod
    def validate_start_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("start_url must start with http:// or https://")
        return value

    @field_validator("parser_rules")
    @classmethod
    def validate_parser_rules(cls, value: str | None) -> str | None:
        return validate_parser_rules_str(value)


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    start_url: str | None = Field(default=None, min_length=1, max_length=2048)
    parser_rules: str | None = Field(default=None, max_length=131072)
    cron_expr: str | None = Field(default=None, min_length=1, max_length=100)
    status: TaskStatus | None = None

    @field_validator("start_url")
    @classmethod
    def validate_start_url(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith(("http://", "https://")):
            raise ValueError("start_url must start with http:// or https://")
        return value

    @field_validator("parser_rules")
    @classmethod
    def validate_parser_rules(cls, value: str | None) -> str | None:
        return validate_parser_rules_str(value)


class TaskRead(TaskBase):
    id: int
    last_run_status: str | None = None
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error_message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("last_run_at", "last_success_at", "created_at", when_used="json")
    def _serialize_times_utc_z(self, value: datetime | None) -> str | None:
        return dt_to_utc_iso_z(value)


class TaskRunPayload(BaseModel):
    task_id: int
    status: str
    recovered_stale_run: bool = False


class RunAllEnabledPayload(BaseModel):
    """Result of enqueueing a manual run for every enabled task."""

    queued_task_ids: list[int] = Field(default_factory=list)
    skipped_task_ids: list[int] = Field(default_factory=list)
    recovered_task_ids: list[int] = Field(default_factory=list)
    quarantined_task_ids: list[int] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
