from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.dependencies import get_current_session, require_admin
from app.repositories.keyword_rule_repo import KeywordRepository
from app.schemas.common import ApiResponse
from app.schemas.keyword_rule import (
    KeywordRuleCreate,
    KeywordRuleListResponse,
    KeywordRuleResponse,
    KeywordRuleUpdate,
)
from app.services.keyword_rule_service import KeywordService

router = APIRouter(
    prefix="/keywords",
    tags=["Keywords"],
    dependencies=[Depends(get_current_session)],
)


def get_keyword_service(session: AsyncSession = Depends(get_db_session)) -> KeywordService:
    repo = KeywordRepository(session)
    return KeywordService(repo)


@router.get("", response_model=ApiResponse[KeywordRuleListResponse])
async def list_keywords(
    service: KeywordService = Depends(get_keyword_service),
):
    rules = list(await service.list_rules())
    default_total = sum(1 for rule in rules if rule.is_default)
    return ApiResponse(
        data=KeywordRuleListResponse(
            items=rules,
            total=len(rules),
            default_total=default_total,
            custom_total=len(rules) - default_total,
        )
    )


@router.post(
    "",
    response_model=ApiResponse[KeywordRuleResponse],
    dependencies=[Depends(require_admin)],
)
async def create_keyword(dto: KeywordRuleCreate, service: KeywordService = Depends(get_keyword_service)):
    rule = await service.create_rule(dto)
    return ApiResponse(data=KeywordRuleResponse.model_validate(rule))


@router.put(
    "/{rule_id}",
    response_model=ApiResponse[KeywordRuleResponse],
    dependencies=[Depends(require_admin)],
)
async def update_keyword(rule_id: int, dto: KeywordRuleUpdate, service: KeywordService = Depends(get_keyword_service)):
    rule = await service.update_rule(rule_id, dto)
    return ApiResponse(data=KeywordRuleResponse.model_validate(rule))


@router.delete(
    "/{rule_id}",
    response_model=ApiResponse[dict],
    dependencies=[Depends(require_admin)],
)
async def delete_keyword(rule_id: int, service: KeywordService = Depends(get_keyword_service)):
    await service.delete_rule(rule_id)
    return ApiResponse(data={"success": True})


@router.post(
    "/{rule_id}/toggle",
    response_model=ApiResponse[KeywordRuleResponse],
    dependencies=[Depends(require_admin)],
)
async def toggle_keyword(rule_id: int, service: KeywordService = Depends(get_keyword_service)):
    rule = await service._repo.get_by_id(rule_id)
    if not rule:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Keyword not found.")
    updated = await service.update_rule(rule_id, KeywordRuleUpdate(is_active=not rule.is_active))
    return ApiResponse(data=KeywordRuleResponse.model_validate(updated))
