from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import (
    get_current_session,
    get_data_service,
    get_notice_service,
    require_admin,
)
from app.schemas.common import ApiResponse, PageData
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
    month: str | None = Query(default=None, pattern=MONTH_PATTERN),
    source_site: str | None = Query(default=None),
    keyword_hit: bool | None = Query(default=None),
    high_priority: bool | None = Query(default=None),
    high_quality: bool | None = Query(default=None),
    project_signal: ProjectSignal | None = Query(default=None),
    service: NoticeService = Depends(get_notice_service),
) -> ApiResponse[PageData[NoticeListItem]]:
    return ApiResponse(
        data=await service.list_notices(
            page=page,
            page_size=page_size,
            keyword=keyword,
            category=category,
            review_status=review_status,
            archived=archived,
            captured_today=captured_today,
            month=month,
            source_site=source_site,
            keyword_hit=keyword_hit,
            high_priority=high_priority,
            high_quality=high_quality,
            project_signal=project_signal,
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
    source_site: str | None = Query(default=None),
    keyword_hit: bool | None = Query(default=None),
    high_priority: bool | None = Query(default=None),
    high_quality: bool | None = Query(default=None),
    project_signal: ProjectSignal | None = Query(default=None),
    service: NoticeService = Depends(get_notice_service),
) -> ApiResponse[list[NoticeMonthOption]]:
    return ApiResponse(
        data=await service.list_months(
            keyword=keyword,
            category=category,
            review_status=review_status,
            archived=archived,
            captured_today=captured_today,
            source_site=source_site,
            keyword_hit=keyword_hit,
            high_priority=high_priority,
            high_quality=high_quality,
            project_signal=project_signal,
        )
    )


@router.get("/{notice_id}", response_model=ApiResponse[NoticeRead])
async def get_notice(
    notice_id: int,
    service: NoticeService = Depends(get_notice_service),
) -> ApiResponse[NoticeRead]:
    try:
        return ApiResponse(data=await service.get_notice(notice_id))
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
    data_service: DataService = Depends(get_data_service),
    notice_service: NoticeService = Depends(get_notice_service),
) -> ApiResponse[NoticeRead]:
    try:
        await data_service.update_review(notice_id, payload)
        return ApiResponse(data=await notice_service.get_notice(notice_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


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
