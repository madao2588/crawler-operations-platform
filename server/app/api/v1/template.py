from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import (
    get_current_session,
    get_template_service,
    require_admin,
)
from app.schemas.common import ApiResponse, EmptyPayload
from app.schemas.template import (
    TaskTemplateCreate,
    TaskTemplateRead,
    TaskTemplateUpdate,
    TestTemplateRequest,
    TestTemplateResponse,
)
from app.services.template_service import TemplateService
from app.engine.test_pipeline import test_run

router = APIRouter(
    prefix="/templates",
    tags=["templates"],
    dependencies=[Depends(get_current_session)],
)


@router.post(
    "/test",
    response_model=ApiResponse[TestTemplateResponse],
    dependencies=[Depends(require_admin)],
)
async def test_template_rules(
    payload: TestTemplateRequest,
) -> ApiResponse[TestTemplateResponse]:
    result = await test_run(payload.start_url, payload.parser_rules)
    return ApiResponse(data=TestTemplateResponse(**result))


@router.get("/tasks", response_model=ApiResponse[list[TaskTemplateRead]])
async def list_task_templates(
    service: TemplateService = Depends(get_template_service),
) -> ApiResponse[list[TaskTemplateRead]]:
    return ApiResponse(data=await service.list_task_templates())


@router.post(
    "/tasks",
    response_model=ApiResponse[TaskTemplateRead],
    dependencies=[Depends(require_admin)],
)
async def create_task_template(
    payload: TaskTemplateCreate,
    service: TemplateService = Depends(get_template_service),
) -> ApiResponse[TaskTemplateRead]:
    try:
        return ApiResponse(data=await service.create_task_template(payload))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/tasks/{template_id}",
    response_model=ApiResponse[TaskTemplateRead],
    dependencies=[Depends(require_admin)],
)
async def update_task_template(
    template_id: str,
    payload: TaskTemplateUpdate,
    service: TemplateService = Depends(get_template_service),
) -> ApiResponse[TaskTemplateRead]:
    try:
        return ApiResponse(data=await service.update_task_template(template_id, payload))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.delete(
    "/tasks/{template_id}",
    response_model=ApiResponse[EmptyPayload],
    dependencies=[Depends(require_admin)],
)
async def delete_task_template(
    template_id: str,
    service: TemplateService = Depends(get_template_service),
) -> ApiResponse[EmptyPayload]:
    try:
        await service.delete_task_template(template_id)
        return ApiResponse(data=EmptyPayload())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/tasks/{template_id}/use",
    response_model=ApiResponse[TaskTemplateRead],
    dependencies=[Depends(require_admin)],
)
async def track_task_template_use(
    template_id: str,
    service: TemplateService = Depends(get_template_service),
) -> ApiResponse[TaskTemplateRead]:
    try:
        return ApiResponse(data=await service.track_task_template_use(template_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
