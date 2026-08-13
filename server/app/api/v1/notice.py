from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import (
    get_current_session,
    get_data_service,
    get_notice_service,
    require_admin,
)
from app.schemas.common import ApiResponse, PageData
from app.schemas.auth import AuthSessionRead
from app.schemas.data import DataReviewUpdate
from app.schemas.notice import (
    NoticeListItem,
    NoticeMonthOption,
    NoticeRead,
    NoticeSnapshotRead,
    NoticeSourceSiteOption,
)
from app.services.data_service import DataService
from app.services.notice_service import NoticeService

router = APIRouter(
    prefix="/notices",
    tags=["notices"],
    dependencies=[Depends(get_current_session)],
)

ProjectSignal = Literal["申报通知", "结果公示", "其他项目线索"]
MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


@router.get("", response_model=ApiResponse[PageData[NoticeListItem]])
async def list_notices(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    keyword: str | None = Query(default=None),
    category: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    archived: bool | None = Query(default=None),
    captured_today: bool | None = Query(default=None),
    business_today: bool | None = Query(default=None),
    business_week: bool | None = Query(default=None),
    month: str | None = Query(default=None, pattern=MONTH_PATTERN),
    source_site: str | None = Query(default=None),
    keyword_hit: bool | None = Query(default=None),
    high_priority: bool | None = Query(default=None),
    high_quality: bool | None = Query(default=None),
    project_signal: ProjectSignal | None = Query(default=None),
    focused_only: bool | None = Query(default=None),
    session_data: AuthSessionRead = Depends(get_current_session),
    service: NoticeService = Depends(get_notice_service),
) -> ApiResponse[PageData[NoticeListItem]]:
    resolved_user_id = getattr(getattr(session_data, "user", None), "id", None)
    resolved_focused_only = focused_only if isinstance(focused_only, bool) else None
    return ApiResponse(
        data=await service.list_notices(
            page=page,
            page_size=page_size,
            keyword=keyword,
            category=category,
            review_status=review_status,
            archived=archived,
            captured_today=captured_today,
            business_today=business_today,
            business_week=business_week,
            month=month,
            source_site=source_site,
            keyword_hit=keyword_hit,
            high_priority=high_priority,
            high_quality=high_quality,
            project_signal=project_signal,
            focused_only=resolved_focused_only,
            user_id=resolved_user_id,
        )
    )


@router.get(
    "/source-sites",
    response_model=ApiResponse[list[NoticeSourceSiteOption]],
)
async def list_source_sites(
    service: NoticeService = Depends(get_notice_service),
) -> ApiResponse[list[NoticeSourceSiteOption]]:
    return ApiResponse(data=await service.list_source_sites())


@router.get(
    "/months",
    response_model=ApiResponse[list[NoticeMonthOption]],
)
async def list_notice_months(
    keyword: str | None = Query(default=None),
    category: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    archived: bool | None = Query(default=None),
    captured_today: bool | None = Query(default=None),
    business_today: bool | None = Query(default=None),
    business_week: bool | None = Query(default=None),
    source_site: str | None = Query(default=None),
    keyword_hit: bool | None = Query(default=None),
    high_priority: bool | None = Query(default=None),
    high_quality: bool | None = Query(default=None),
    project_signal: ProjectSignal | None = Query(default=None),
    focused_only: bool | None = Query(default=None),
    session_data: AuthSessionRead = Depends(get_current_session),
    service: NoticeService = Depends(get_notice_service),
) -> ApiResponse[list[NoticeMonthOption]]:
    resolved_user_id = getattr(getattr(session_data, "user", None), "id", None)
    resolved_focused_only = focused_only if isinstance(focused_only, bool) else None
    return ApiResponse(
        data=await service.list_months(
            keyword=keyword,
            category=category,
            review_status=review_status,
            archived=archived,
            captured_today=captured_today,
            business_today=business_today,
            business_week=business_week,
            source_site=source_site,
            keyword_hit=keyword_hit,
            high_priority=high_priority,
            high_quality=high_quality,
            project_signal=project_signal,
            focused_only=resolved_focused_only,
            user_id=resolved_user_id,
        )
    )


@router.get("/{notice_id}", response_model=ApiResponse[NoticeRead])
async def get_notice(
    notice_id: int,
    session_data: AuthSessionRead = Depends(get_current_session),
    service: NoticeService = Depends(get_notice_service),
) -> ApiResponse[NoticeRead]:
    try:
        return ApiResponse(data=await service.get_notice(notice_id, user_id=session_data.user.id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch(
    "/{notice_id}/review",
    response_model=ApiResponse[NoticeRead],
    dependencies=[Depends(require_admin)],
)
async def update_notice_review(
    notice_id: int,
    payload: DataReviewUpdate,
    admin: AuthSessionRead = Depends(require_admin),
    data_service: DataService = Depends(get_data_service),
    notice_service: NoticeService = Depends(get_notice_service),
) -> ApiResponse[NoticeRead]:
    try:
        await data_service.update_review(notice_id, payload)
        return ApiResponse(data=await notice_service.get_notice(notice_id, user_id=admin.user.id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/{notice_id}/focus", response_model=ApiResponse[NoticeRead])
async def add_notice_focus(
    notice_id: int,
    session_data: AuthSessionRead = Depends(get_current_session),
    service: NoticeService = Depends(get_notice_service),
) -> ApiResponse[NoticeRead]:
    try:
        return ApiResponse(
            data=await service.set_focus(notice_id, user_id=session_data.user.id, focused=True)
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{notice_id}/focus", response_model=ApiResponse[NoticeRead])
async def remove_notice_focus(
    notice_id: int,
    session_data: AuthSessionRead = Depends(get_current_session),
    service: NoticeService = Depends(get_notice_service),
) -> ApiResponse[NoticeRead]:
    try:
        return ApiResponse(
            data=await service.set_focus(notice_id, user_id=session_data.user.id, focused=False)
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{notice_id}/snapshot", response_model=ApiResponse[NoticeSnapshotRead])
async def get_notice_snapshot(
    notice_id: int,
    service: NoticeService = Depends(get_notice_service),
) -> ApiResponse[NoticeSnapshotRead]:
    try:
        return ApiResponse(data=await service.get_notice_snapshot(notice_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
