from fastapi import APIRouter, Depends

from app.dependencies import get_current_session, get_data_service
from app.schemas.common import ApiResponse, StatsOverview
from app.services.data_service import DataService

router = APIRouter(
    prefix="/stats",
    tags=["stats"],
    dependencies=[Depends(get_current_session)],
)


@router.get("/overview", response_model=ApiResponse[StatsOverview])
async def overview(
    service: DataService = Depends(get_data_service),
) -> ApiResponse[StatsOverview]:
    data = await service.get_overview_stats()
    return ApiResponse(data=data)
