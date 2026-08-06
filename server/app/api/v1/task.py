from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies import get_current_session, get_task_service, require_admin
from app.schemas.common import ApiResponse, EmptyPayload, PageData
from app.schemas.task import RunAllEnabledPayload, TaskCreate, TaskRead, TaskRunPayload, TaskUpdate
from app.services.crawl_service import TaskRunConflictError
from app.services.task_service import TaskBusyError, TaskService

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"],
    dependencies=[Depends(get_current_session)],
)


@router.get("", response_model=ApiResponse[PageData[TaskRead]])
async def list_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    enabled: str = Query(default="all"),
    last_run: str = Query(default="all"),
    sort_by: str = Query(default="id"),
    sort_dir: str = Query(default="desc"),
    service: TaskService = Depends(get_task_service),
) -> ApiResponse[PageData[TaskRead]]:
    if enabled not in {"all", "enabled", "disabled"}:
        raise HTTPException(status_code=400, detail="invalid enabled filter")
    if last_run not in {"all", "success", "partial", "failed", "active", "never"}:
        raise HTTPException(status_code=400, detail="invalid last_run filter")
    if sort_by not in {"id", "name", "last_run_at", "created_at"}:
        raise HTTPException(status_code=400, detail="invalid sort_by")
    if sort_dir not in {"asc", "desc"}:
        raise HTTPException(status_code=400, detail="invalid sort_dir")
    data = await service.list_tasks(
        page=page,
        page_size=page_size,
        search=search,
        enabled=enabled,
        last_run=last_run,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    return ApiResponse(data=data)


@router.post(
    "/run-enabled",
    response_model=ApiResponse[RunAllEnabledPayload],
    dependencies=[Depends(require_admin)],
)
async def run_enabled_tasks(
    service: TaskService = Depends(get_task_service),
) -> ApiResponse[RunAllEnabledPayload]:
    """Enqueue a manual run for every enabled task (skips busy ones)."""
    data = await service.run_all_enabled_tasks_now()
    return ApiResponse(data=data)


@router.get("/{task_id}", response_model=ApiResponse[TaskRead])
async def get_task(
    task_id: int,
    service: TaskService = Depends(get_task_service),
) -> ApiResponse[TaskRead]:
    try:
        data = await service.get_task(task_id)
        return ApiResponse(data=data)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=ApiResponse[TaskRead], dependencies=[Depends(require_admin)])
async def create_task(
    payload: TaskCreate,
    service: TaskService = Depends(get_task_service),
) -> ApiResponse[TaskRead]:
    try:
        data = await service.create_task(payload)
        return ApiResponse(data=data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/{task_id}",
    response_model=ApiResponse[TaskRead],
    dependencies=[Depends(require_admin)],
)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    service: TaskService = Depends(get_task_service),
) -> ApiResponse[TaskRead]:
    try:
        data = await service.update_task(task_id, payload)
        return ApiResponse(data=data)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete(
    "/{task_id}",
    response_model=ApiResponse[EmptyPayload],
    dependencies=[Depends(require_admin)],
)
async def delete_task(
    task_id: int,
    service: TaskService = Depends(get_task_service),
) -> ApiResponse[EmptyPayload]:
    try:
        data = await service.delete_task(task_id)
        return ApiResponse(data=data)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TaskBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/{task_id}/run",
    response_model=ApiResponse[TaskRunPayload],
    dependencies=[Depends(require_admin)],
)
async def run_task(
    task_id: int,
    service: TaskService = Depends(get_task_service),
) -> ApiResponse[TaskRunPayload]:
    try:
        data = await service.run_task_now(task_id)
        return ApiResponse(data=data)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TaskRunConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
