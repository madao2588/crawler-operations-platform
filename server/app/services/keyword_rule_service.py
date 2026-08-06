from app.repositories.keyword_rule_repo import KeywordRepository
from app.schemas.keyword_rule import KeywordRuleCreate, KeywordRuleUpdate
from app.utils.notice import DEFAULT_NOTICE_KEYWORDS, HIGH_PRIORITY_KEYWORDS
from fastapi import HTTPException


class KeywordService:
    def __init__(self, kw_repo: KeywordRepository) -> None:
        self._repo = kw_repo

    async def list_rules(self):
        rules = await self._repo.all()
        return rules

    async def ensure_seed_data(self) -> None:
        high_priority_words = {word.casefold() for word in HIGH_PRIORITY_KEYWORDS}
        await self._repo.ensure_defaults(
            [(word, word.casefold() in high_priority_words) for word in DEFAULT_NOTICE_KEYWORDS]
        )

    async def create_rule(self, dto: KeywordRuleCreate):
        existing = await self._repo.get_by_word(dto.word)
        if existing:
            raise HTTPException(status_code=400, detail="Keyword already exists.")
        return await self._repo.create(dto)

    async def update_rule(self, rule_id: int, dto: KeywordRuleUpdate):
        rule = await self._repo.get_by_id(rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail="Keyword not found.")

        if dto.word is not None and dto.word != rule.word:
            if rule.is_default:
                raise HTTPException(
                    status_code=400,
                    detail="Default keywords cannot be renamed.",
                )
            existing = await self._repo.get_by_word(dto.word)
            if existing:
                raise HTTPException(status_code=400, detail="Keyword already exists.")

        return await self._repo.update(rule, dto)

    async def delete_rule(self, rule_id: int):
        rule = await self._repo.get_by_id(rule_id)
        if not rule:
            raise HTTPException(status_code=404, detail="Keyword not found.")
        if rule.is_default:
            raise HTTPException(
                status_code=400,
                detail="Default keywords cannot be deleted; disable the rule instead.",
            )
        await self._repo.delete(rule)
        return {"success": True}
