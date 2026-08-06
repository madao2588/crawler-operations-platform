import pytest
from fastapi import HTTPException

from app.repositories.keyword_rule_repo import KeywordRepository
from app.schemas.keyword_rule import KeywordRuleUpdate
from app.services.keyword_rule_service import KeywordService
from app.utils.notice import DEFAULT_NOTICE_KEYWORDS, HIGH_PRIORITY_KEYWORDS


@pytest.mark.asyncio
async def test_default_keywords_are_seeded_as_real_rules(async_session) -> None:
    service = KeywordService(KeywordRepository(async_session))

    await service.ensure_seed_data()
    rules = list(await service.list_rules())
    defaults = [rule for rule in rules if rule.is_default]

    assert {rule.word for rule in defaults} == set(DEFAULT_NOTICE_KEYWORDS)
    assert {rule.word for rule in defaults if rule.is_high_priority} == set(HIGH_PRIORITY_KEYWORDS)
    assert all(rule.is_active for rule in defaults)


@pytest.mark.asyncio
async def test_default_keyword_seed_is_idempotent_and_preserves_operator_settings(
    async_session,
) -> None:
    service = KeywordService(KeywordRepository(async_session))
    await service.ensure_seed_data()
    default_rule = await service._repo.get_by_word(DEFAULT_NOTICE_KEYWORDS[0])
    assert default_rule is not None

    await service.update_rule(
        default_rule.id,
        KeywordRuleUpdate(is_active=False, is_high_priority=False),
    )
    await service.ensure_seed_data()

    rules = list(await service.list_rules())
    preserved = next(rule for rule in rules if rule.id == default_rule.id)
    assert len([rule for rule in rules if rule.is_default]) == len(DEFAULT_NOTICE_KEYWORDS)
    assert preserved.is_active is False
    assert preserved.is_high_priority is False


@pytest.mark.asyncio
async def test_default_keyword_can_be_configured_but_not_renamed_or_deleted(
    async_session,
) -> None:
    service = KeywordService(KeywordRepository(async_session))
    await service.ensure_seed_data()
    default_rule = await service._repo.get_by_word(DEFAULT_NOTICE_KEYWORDS[0])
    assert default_rule is not None

    updated = await service.update_rule(
        default_rule.id,
        KeywordRuleUpdate(is_active=False, is_high_priority=False),
    )
    assert updated.is_active is False
    assert updated.is_high_priority is False

    with pytest.raises(HTTPException) as rename_error:
        await service.update_rule(
            default_rule.id,
            KeywordRuleUpdate(word="重命名后的默认词"),
        )
    assert rename_error.value.status_code == 400

    with pytest.raises(HTTPException) as delete_error:
        await service.delete_rule(default_rule.id)
    assert delete_error.value.status_code == 400
