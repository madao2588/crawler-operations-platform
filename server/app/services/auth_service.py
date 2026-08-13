from __future__ import annotations

import base64
import binascii
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    password_hash_needs_upgrade,
    verify_password,
)
from app.models.auth import User, UserSession
from app.repositories.auth_repo import AuthRepository
from app.schemas.auth import (
    AuthSessionRead,
    LoginPayload,
    UserAdminRead,
    UserCreatePayload,
    UserRead,
)
from app.services.login_guard_service import LoginGuardService


MAX_AVATAR_BYTES = 2 * 1024 * 1024
MAX_AVATAR_BASE64_CHARS = ((MAX_AVATAR_BYTES + 2) // 3) * 4


class AuthService:
    def __init__(self, auth_repo: AuthRepository, login_guard: LoginGuardService | None = None):
        self.auth_repo = auth_repo
        self.settings = get_settings()
        self.login_guard = login_guard or LoginGuardService()

    async def ensure_default_admin(self) -> None:
        username = (self.settings.bootstrap_admin_username or "").strip()
        password = self.settings.bootstrap_admin_password
        if not username and not password:
            return
        if not username or not password:
            raise ValueError(
                "Bootstrap admin requires both CRAWLER_BOOTSTRAP_ADMIN_USERNAME "
                "and CRAWLER_BOOTSTRAP_ADMIN_PASSWORD.",
            )

        existing_user = await self.auth_repo.get_user_by_username(username)
        if existing_user is not None:
            if existing_user.role != "admin" or not existing_user.is_active:
                await self.auth_repo.update_user_access(
                    existing_user,
                    role="admin",
                    is_active=True,
                )
            return

        password_hash, password_salt = hash_password(password)
        await self.auth_repo.create_user(
            username=username,
            password_hash=password_hash,
            password_salt=password_salt,
            role="admin",
        )

    async def login(self, payload: LoginPayload) -> AuthSessionRead:
        self.login_guard.ensure_allowed(payload.username)
        user = await self.auth_repo.get_user_by_username(payload.username)
        if user is None:
            self.login_guard.record_failure(payload.username)
            raise ValueError("用户名或密码不正确")

        if not verify_password(payload.password, user.password_salt, user.password_hash):
            self.login_guard.record_failure(payload.username)
            raise ValueError("用户名或密码不正确")
        if not user.is_active:
            raise ValueError("账号已停用，请联系管理员")

        if password_hash_needs_upgrade(user.password_salt):
            upgraded_hash, upgraded_salt = hash_password(payload.password)
            user = await self.auth_repo.update_user_password(
                user,
                password_hash=upgraded_hash,
                password_salt=upgraded_salt,
            )

        token = generate_session_token()
        expires_at = datetime.now(UTC) + timedelta(days=self.settings.session_ttl_days)
        session_obj = await self.auth_repo.create_session(
            user,
            hash_session_token(token),
            expires_at,
        )
        self.login_guard.record_success(payload.username)
        return self._build_session_response(user, session_obj, access_token=token)

    async def get_session(self, token: str) -> AuthSessionRead:
        token_hash = hash_session_token(token)
        session_obj = await self.auth_repo.get_session_by_token(token_hash)
        if session_obj is None:
            raise PermissionError("登录已过期，请重新登录")

        if session_obj.expires_at.tzinfo is None:
            expires_at = session_obj.expires_at.replace(tzinfo=UTC)
        else:
            expires_at = session_obj.expires_at.astimezone(UTC)

        if expires_at <= datetime.now(UTC):
            await self.auth_repo.delete_session_by_token(token_hash)
            raise PermissionError("登录已过期，请重新登录")

        await self.auth_repo.touch_session(session_obj)
        user = await self.auth_repo.get_user_by_id(session_obj.user_id)
        if user is None or not user.is_active:
            await self.auth_repo.delete_session_by_token(token_hash)
            raise PermissionError("登录已失效，请重新登录")

        return self._build_session_response(user, session_obj, access_token=token)

    async def logout(self, token: str) -> None:
        await self.auth_repo.delete_session_by_token(hash_session_token(token))

    async def list_users(self) -> list[UserAdminRead]:
        users = await self.auth_repo.list_users()
        return [UserAdminRead.model_validate(user) for user in users]

    async def create_user(self, payload: UserCreatePayload) -> UserAdminRead:
        username = payload.username.strip()
        if len(username) < 2:
            raise ValueError("用户名至少需要 2 个字符")
        if await self.auth_repo.get_user_by_username(username) is not None:
            raise ValueError("用户名已存在")

        password_hash, password_salt = hash_password(payload.password)
        user = await self.auth_repo.create_user(
            username=username,
            password_hash=password_hash,
            password_salt=password_salt,
            role=payload.role,
        )
        return UserAdminRead.model_validate(user)

    async def update_password(
        self,
        session_data: AuthSessionRead,
        *,
        current_password: str,
        new_password: str,
    ) -> None:
        user = await self.auth_repo.get_user_by_id(session_data.user.id)
        if user is None or not user.is_active:
            raise PermissionError("登录已失效，请重新登录")
        if not verify_password(current_password, user.password_salt, user.password_hash):
            raise ValueError("当前密码不正确")
        if verify_password(new_password, user.password_salt, user.password_hash):
            raise ValueError("新密码不能与当前密码相同")

        password_hash, password_salt = hash_password(new_password)
        await self.auth_repo.update_user_password(
            user,
            password_hash=password_hash,
            password_salt=password_salt,
        )
        await self.auth_repo.delete_sessions_by_user_id(user.id)

    async def reset_user_password(self, user_id: int, new_password: str) -> None:
        user = await self.auth_repo.get_user_by_id(user_id)
        if user is None:
            raise LookupError("账号不存在")
        password_hash, password_salt = hash_password(new_password)
        await self.auth_repo.update_user_password(
            user,
            password_hash=password_hash,
            password_salt=password_salt,
        )
        await self.auth_repo.delete_sessions_by_user_id(user.id)

    async def update_user_status(
        self,
        session_data: AuthSessionRead,
        *,
        user_id: int,
        is_active: bool,
    ) -> UserAdminRead:
        user = await self.auth_repo.get_user_by_id(user_id)
        if user is None:
            raise LookupError("账号不存在")
        if user.id == session_data.user.id and not is_active:
            raise ValueError("不能停用当前登录的管理员账号")

        if user.is_active != is_active:
            user = await self.auth_repo.update_user_status(user, is_active)
            if not is_active:
                await self.auth_repo.delete_sessions_by_user_id(user.id)
        return UserAdminRead.model_validate(user)

    async def update_avatar(
        self,
        session_data: AuthSessionRead,
        avatar_base64: str | None,
    ) -> AuthSessionRead:
        normalized_avatar = self._normalize_avatar(avatar_base64)
        user = await self.auth_repo.get_user_by_id(session_data.user.id)
        if user is None or not user.is_active:
            raise PermissionError("登录已失效，请重新登录")

        if normalized_avatar != user.avatar_base64:
            user = await self.auth_repo.update_user_avatar(user, normalized_avatar)

        return session_data.model_copy(
            update={"user": UserRead.model_validate(user)},
        )

    def _build_session_response(
        self,
        user: User,
        session_obj: UserSession,
        *,
        access_token: str,
    ) -> AuthSessionRead:
        return AuthSessionRead(
            access_token=access_token,
            expires_at=session_obj.expires_at,
            user=UserRead(
                id=user.id,
                username=user.username,
                avatar_base64=user.avatar_base64,
                role=user.role,
                is_active=user.is_active,
            ),
        )

    def _normalize_avatar(self, avatar_base64: str | None) -> str | None:
        if avatar_base64 is None:
            return None

        trimmed = avatar_base64.strip()
        if not trimmed:
            return None

        if len(trimmed) > MAX_AVATAR_BASE64_CHARS:
            raise ValueError("头像图片不能超过 2MB")

        try:
            raw = base64.b64decode(trimmed, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("头像图片数据无效") from exc

        if len(raw) > MAX_AVATAR_BYTES:
            raise ValueError("头像图片不能超过 2MB")

        is_jpeg = raw.startswith(b"\xff\xd8\xff")
        is_png = raw.startswith(b"\x89PNG\r\n\x1a\n")
        is_webp = raw.startswith(b"RIFF") and raw[8:12] == b"WEBP"
        if not (is_jpeg or is_png or is_webp):
            raise ValueError("仅支持 PNG、JPG 或 WebP 图片")
        return trimmed
