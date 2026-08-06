from fastapi import APIRouter, Depends, Query

from app.dependencies import get_current_session, get_data_service
from app.schemas.common import ApiResponse, LogRead, LogSummary, PageData
from app.services.data_service import DataService

router = APIRouter(
    prefix="/logs",
    tags=["logs"],
    dependencies=[Depends(get_current_session)],
)


@router.get("", response_model=ApiResponse[PageData[LogRead]])
async def list_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    task_id: int | None = Query(default=None),
    level: str | None = Query(default=None),
    message_contains: str | None = Query(default=None, max_length=500),
    only_summary: bool = Query(default=False),
    service: DataService = Depends(get_data_service),
) -> ApiResponse[PageData[LogRead]]:
    data = await service.list_logs(
        page=page,
        page_size=page_size,
        task_id=task_id,
        level=level,
        message_contains=message_contains,
        only_summary=only_summary,
    )
    return ApiResponse(data=data)


@router.get("/summary", response_model=ApiResponse[LogSummary])
async def get_log_summary(
    service: DataService = Depends(get_data_service),
) -> ApiResponse[LogSummary]:
    return ApiResponse(data=await service.get_log_summary())
