import json

import pytest

from app.repositories.data_repo import DataRepository
from app.services.data_service import DataService
from app.services.notice_service import NoticeService


class _NoKeywordRules:
    async def get_active(self):
        return []


@pytest.mark.asyncio
async def test_competitor_metadata_roundtrips_through_notice_service(async_session) -> None:
    repository = DataRepository(async_session)
    metadata = {
        "kind": "competitor_intelligence",
        "source": "PubMed",
        "topic": "脑胶质瘤",
        "external_id": "12345678",
        "doi": "10.1000/example",
        "drugs": ["Examplemab"],
        "development_stage": "临床Ⅱ期",
        "evidence_level": "临床试验证据",
    }
    stored = await repository.create(
        task_id=1,
        title="Targeted therapy for glioblastoma",
        content_html="<p>Abstract</p>",
        content_text="Abstract",
        source_url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
        snapshot_path=None,
        quality_score=90,
        content_hash="pubmed-12345678",
        category="竞品信息",
        ai_summary="Abstract",
        metadata_json=json.dumps(metadata, ensure_ascii=False),
    )

    notice = await NoticeService(repository, _NoKeywordRules()).get_notice(stored.id)

    assert notice.metadata == metadata

    export = await DataService(
        repository,
        task_repo=None,  # type: ignore[arg-type]
        log_repo=None,  # type: ignore[arg-type]
    ).export_collected_data_excel_compatible(
        task_id=1,
        limit=10,
    )
    export_text = export.decode("utf-8")
    assert "研究方向" in export_text
    assert "PMID" in export_text
    assert "药物/化学物质" in export_text
    assert "研发阶段" in export_text
    assert "证据等级" in export_text
    assert "脑胶质瘤" in export_text
    assert "12345678" in export_text
    assert "Examplemab" in export_text
