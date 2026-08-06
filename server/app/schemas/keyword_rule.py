from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.schemas.serialization import dt_to_utc_iso_z


class KeywordRuleBase(BaseModel):
    word: str = Field(..., min_length=1, max_length=100, description="The keyword itself")
    is_high_priority: bool = Field(
        False,
        description="Whether matches mark notices as business priority",
    )
    is_active: bool = Field(True, description="Whether this rule is enabled")


class KeywordRuleCreate(KeywordRuleBase):
    pass


class KeywordRuleUpdate(BaseModel):
    word: str | None = Field(None, min_length=1, max_length=100)
    is_high_priority: bool | None = None
    is_active: bool | None = None


class KeywordRuleResponse(KeywordRuleBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_default: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at", when_used="json")
    def _serialize_times_utc_z(self, value: datetime) -> str:
        return dt_to_utc_iso_z(value) or ""


class KeywordRuleListResponse(BaseModel):
    items: list[KeywordRuleResponse]
    total: int
    default_total: int
    custom_total: int
