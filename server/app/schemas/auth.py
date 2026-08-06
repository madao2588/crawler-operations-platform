from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


UserRole = Literal["admin", "user"]


class LoginPayload(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=255)
    avatar_base64: str | None = None


class AvatarUpdatePayload(BaseModel):
    avatar_base64: str | None = None


class PasswordUpdatePayload(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=255)
    new_password: str = Field(..., min_length=6, max_length=255)


class PasswordResetPayload(BaseModel):
    new_password: str = Field(..., min_length=6, max_length=255)


class UserCreatePayload(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    password: str = Field(..., min_length=6, max_length=255)
    role: UserRole = "user"


class UserStatusUpdatePayload(BaseModel):
    is_active: bool


class UserRead(BaseModel):
    id: int
    username: str
    avatar_base64: str | None = None
    role: UserRole
    is_active: bool

    model_config = {"from_attributes": True}


class UserAdminRead(UserRead):
    created_at: datetime


class AuthSessionRead(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserRead
