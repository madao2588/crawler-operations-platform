from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import (
    get_auth_service,
    get_bearer_token,
    get_current_session,
    require_admin,
)
from app.schemas.auth import (
    AuthSessionRead,
    AvatarUpdatePayload,
    LoginPayload,
    PasswordResetPayload,
    PasswordUpdatePayload,
    UserAdminRead,
    UserCreatePayload,
    UserStatusUpdatePayload,
)
from app.schemas.common import ApiResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=ApiResponse[AuthSessionRead])
async def login(
    payload: LoginPayload,
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[AuthSessionRead]:
    try:
        session_data = await service.login(payload)
        return ApiResponse(data=session_data)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.get("/me", response_model=ApiResponse[AuthSessionRead])
async def me(
    include_avatar: bool = True,
    session_data: AuthSessionRead = Depends(get_current_session),
) -> ApiResponse[AuthSessionRead]:
    if not include_avatar:
        session_data = session_data.model_copy(
            update={
                "user": session_data.user.model_copy(
                    update={"avatar_base64": None},
                )
            }
        )
    return ApiResponse(data=session_data)


@router.patch("/me/avatar", response_model=ApiResponse[AuthSessionRead])
async def update_avatar(
    payload: AvatarUpdatePayload,
    session_data: AuthSessionRead = Depends(get_current_session),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[AuthSessionRead]:
    try:
        updated_session = await service.update_avatar(session_data, payload.avatar_base64)
        return ApiResponse(data=updated_session)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc


@router.patch("/me/password", response_model=ApiResponse[dict[str, str]])
async def update_password(
    payload: PasswordUpdatePayload,
    session_data: AuthSessionRead = Depends(get_current_session),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[dict[str, str]]:
    try:
        await service.update_password(
            session_data,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
        return ApiResponse(data={"message": "密码已修改，请重新登录"})
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.get("/users", response_model=ApiResponse[list[UserAdminRead]])
async def list_users(
    _admin: AuthSessionRead = Depends(require_admin),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[list[UserAdminRead]]:
    return ApiResponse(data=await service.list_users())


@router.post("/users", response_model=ApiResponse[UserAdminRead])
async def create_user(
    payload: UserCreatePayload,
    _admin: AuthSessionRead = Depends(require_admin),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[UserAdminRead]:
    try:
        return ApiResponse(data=await service.create_user(payload))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.patch("/users/{user_id}/status", response_model=ApiResponse[UserAdminRead])
async def update_user_status(
    user_id: int,
    payload: UserStatusUpdatePayload,
    admin: AuthSessionRead = Depends(require_admin),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[UserAdminRead]:
    try:
        return ApiResponse(
            data=await service.update_user_status(
                admin,
                user_id=user_id,
                is_active=payload.is_active,
            )
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post(
    "/users/{user_id}/reset-password",
    response_model=ApiResponse[dict[str, str]],
)
async def reset_user_password(
    user_id: int,
    payload: PasswordResetPayload,
    _admin: AuthSessionRead = Depends(require_admin),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[dict[str, str]]:
    try:
        await service.reset_user_password(user_id, payload.new_password)
        return ApiResponse(data={"message": "密码已重置"})
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/logout", response_model=ApiResponse[dict[str, str]])
async def logout(
    token: str = Depends(get_bearer_token),
    service: AuthService = Depends(get_auth_service),
) -> ApiResponse[dict[str, str]]:
    await service.logout(token)
    return ApiResponse(data={"message": "success"})
