from collections.abc import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.models.keyword_rule import KeywordRule
from app.schemas.keyword_rule import KeywordRuleCreate, KeywordRuleUpdate


class KeywordRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def all(self) -> Sequence[KeywordRule]:
        result = await self._session.execute(select(KeywordRule).order_by(KeywordRule.id.desc()))
        return result.scalars().all()

    async def get_active(self) -> list[KeywordRule]:
        result = await self._session.execute(select(KeywordRule).where(KeywordRule.is_active.is_(True)))
        return list(result.scalars().all())

    async def get_by_id(self, rule_id: int) -> Optional[KeywordRule]:
        return await self._session.get(KeywordRule, rule_id)

    async def get_by_word(self, word: str) -> Optional[KeywordRule]:
        result = await self._session.execute(select(KeywordRule).where(KeywordRule.word == word))
        return result.scalars().first()

    async def create(self, kw_schema: KeywordRuleCreate) -> KeywordRule:
        rule = KeywordRule(
            word=kw_schema.word,
            is_high_priority=kw_schema.is_high_priority,
            is_active=kw_schema.is_active,
            is_default=False,
        )
        self._session.add(rule)
        await self._session.commit()
        await self._session.refresh(rule)
        return rule

    async def update(self, rule: KeywordRule, updates: KeywordRuleUpdate) -> KeywordRule:
        update_data = updates.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(rule, key, value)
        await self._session.commit()
        await self._session.refresh(rule)
        return rule

    async def delete(self, rule: KeywordRule) -> None:
        await self._session.delete(rule)
        await self._session.commit()

    async def ensure_defaults(self, defaults: list[tuple[str, bool]]) -> None:
        existing_rules = list(await self.all())
        existing_by_word = {rule.word.strip().casefold(): rule for rule in existing_rules}
        changed = False

        for word, is_high_priority in defaults:
            existing = existing_by_word.get(word.strip().casefold())
            if existing is not None:
                if not existing.is_default:
                    existing.is_default = True
                    changed = True
                continue

            self._session.add(
                KeywordRule(
                    word=word,
                    is_high_priority=is_high_priority,
                    is_active=True,
                    is_default=True,
                )
            )
            changed = True

        if changed:
            await self._session.commit()
