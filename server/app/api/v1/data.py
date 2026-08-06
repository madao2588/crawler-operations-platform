from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.dependencies import get_current_session, get_data_service, require_admin
from app.schemas.common import ApiResponse, PageData
from app.schemas.data import DataListItem, DataRead, DataReviewUpdate, SnapshotRead
from app.services.data_service import DataService

router = APIRouter(
    prefix="/data",
    tags=["data"],
    dependencies=[Depends(get_current_session)],
)


@router.get("/export/csv")
async def export_collected_data_csv(
    task_id: int | None = Query(default=None),
    limit: int = Query(default=2000, ge=1, le=10000),
    category: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    archived: bool | None = Query(default=None),
    service: DataService = Depends(get_data_service),
) -> Response:
    payload = await service.export_collected_data_csv(
        task_id=task_id,
        limit=limit,
        category=category,
        review_status=review_status,
        archived=archived,
    )
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="collected_data_export.csv"',
        },
    )


@router.get("/export/excel")
async def export_collected_data_excel(
    task_id: int | None = Query(default=None),
    limit: int = Query(default=2000, ge=1, le=10000),
    category: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    archived: bool | None = Query(default=None),
    service: DataService = Depends(get_data_service),
) -> Response:
    payload = await service.export_collected_data_excel_compatible(
        task_id=task_id,
        limit=limit,
        category=category,
        review_status=review_status,
        archived=archived,
    )
    return Response(
        content=payload,
        media_type="application/vnd.ms-excel; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="information_pool_export.xls"',
        },
    )


@router.get("", response_model=ApiResponse[PageData[DataListItem]])
async def list_data(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    task_id: int | None = Query(default=None),
    category: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    archived: bool | None = Query(default=None),
    service: DataService = Depends(get_data_service),
) -> ApiResponse[PageData[DataListItem]]:
    data = await service.list_data(
        page=page,
        page_size=page_size,
        task_id=task_id,
        category=category,
        review_status=review_status,
        archived=archived,
    )
    return ApiResponse(data=data)


@router.patch(
    "/{data_id}/review",
    response_model=ApiResponse[DataRead],
    dependencies=[Depends(require_admin)],
)
async def update_data_review(
    data_id: int,
    payload: DataReviewUpdate,
    service: DataService = Depends(get_data_service),
) -> ApiResponse[DataRead]:
    try:
        return ApiResponse(data=await service.update_review(data_id, payload))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{data_id}", response_model=ApiResponse[DataRead])
async def get_data(
    data_id: int,
    service: DataService = Depends(get_data_service),
) -> ApiResponse[DataRead]:
    try:
        data = await service.get_data(data_id)
        return ApiResponse(data=data)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{data_id}/snapshot", response_model=ApiResponse[SnapshotRead])
async def get_snapshot(
    data_id: int,
    service: DataService = Depends(get_data_service),
) -> ApiResponse[SnapshotRead]:
    try:
        data = await service.get_snapshot_content(data_id)
        return ApiResponse(data=data)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
