from fastapi import APIRouter, Depends

from app.dependencies import get_current_session, get_dashboard_service
from app.schemas.common import ApiResponse
from app.schemas.dashboard import DashboardOverview
from app.services.dashboard_service import DashboardService

router = APIRouter(
    prefix="/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(get_current_session)],
)


@router.get("/overview", response_model=ApiResponse[DashboardOverview])
async def get_dashboard_overview(
    service: DashboardService = Depends(get_dashboard_service),
) -> ApiResponse[DashboardOverview]:
    return ApiResponse(data=await service.get_overview())
