from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.parser_rules import validate_parser_rules_str


class TaskTemplateBase(BaseModel):
    label: str = Field(..., min_length=1, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    start_url: str = Field(..., min_length=1, max_length=2048)
    cron_expr: str = Field(..., min_length=1, max_length=100)
    parser_rules: str | None = Field(default=None, max_length=131072)
    enabled: bool = True
    description: str = Field(..., min_length=1, max_length=500)
    tags: list[str] = Field(default_factory=list)

    @field_validator("parser_rules")
    @classmethod
    def validate_parser_rules(cls, value: str | None) -> str | None:
        return validate_parser_rules_str(value)


class TaskTemplateCreate(TaskTemplateBase):
    id: str | None = Field(default=None, min_length=1)


class TaskTemplateUpdate(TaskTemplateBase):
    pass


class TaskTemplateRead(TaskTemplateBase):
    id: str = Field(..., min_length=1)
    usage_count: int = Field(default=0, ge=0)
    last_used_at: datetime | None = None

    model_config = {"from_attributes": True}


class TestTemplateRequest(BaseModel):
    start_url: str = Field(..., min_length=1, max_length=2048)
    parser_rules: str | None = Field(default=None, max_length=131072)

    @field_validator("parser_rules")
    @classmethod
    def validate_parser_rules(cls, value: str | None) -> str | None:
        return validate_parser_rules_str(value)


class TemplateTestTrace(BaseModel):
    """与生产流水线一致的决策路径摘要，便于本地调规则。"""

    fetch: str | None = None
    content_source: str | None = None
    notes: list[str] = Field(default_factory=list)


class TestTemplateResponse(BaseModel):
    title: str | None = None
    content_text: str | None = None
    content_html: str | None = None
    quality_score: int | None = None
    error: str | None = None
    trace: TemplateTestTrace | None = None
