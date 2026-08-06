import json

import pytest

import app.engine.pipeline as pipeline_mod


def test_pubmed_topic_merge_keeps_cross_topic_article_stable() -> None:
    existing_metadata = json.dumps(
        {
            "kind": "competitor_intelligence",
            "source": "PubMed",
            "topic": "脑胶质瘤",
            "topics": ["脑胶质瘤"],
            "external_id": "12345678",
        },
        ensure_ascii=False,
    )

    assert pipeline_mod._merge_pubmed_topics(
        existing_metadata,
        "降尿酸药物",
    ) == ["脑胶质瘤", "降尿酸药物"]
    assert pipeline_mod._merge_pubmed_topics(
        existing_metadata,
        "脑胶质瘤",
    ) == ["脑胶质瘤"]


class _PubMedTaskRepo:
    def __init__(self, _session) -> None:
        self.task = type(
            "PubMedTask",
            (),
            {
                "id": 1,
                "start_url": "https://pubmed.ncbi.nlm.nih.gov/",
                "parser_rules": json.dumps(
                    {
                        "crawl_mode": "pubmed",
                        "max_results_per_topic": 25,
                        "lookback_days": 730,
                        "topics": [
                            {"name": "脑胶质瘤", "query": "glioma"},
                            {"name": "降尿酸药物", "query": "hyperuricemia"},
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        )()

    async def get_by_id(self, task_id: int):
        if task_id != 1:
            return None
        return self.task


class _FakeDataRepo:
    def __init__(self, _session) -> None:
        pass


class _FakeLogRepo:
    captured_messages: list[str] = []

    def __init__(self, _session) -> None:
        pass

    async def create(self, **kwargs) -> None:
        message = kwargs.get("message")
        if isinstance(message, str):
            self.captured_messages.append(message)


class _FakeSessionCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        _ = (exc_type, exc, tb)
        return False


@pytest.mark.asyncio
async def test_pubmed_mode_uses_structured_collector_and_emits_summary(monkeypatch) -> None:
    _FakeLogRepo.captured_messages.clear()
    captured_rules: list[dict[str, object]] = []

    monkeypatch.setattr(pipeline_mod, "AsyncSessionLocal", lambda: _FakeSessionCtx())
    monkeypatch.setattr(pipeline_mod, "TaskRepository", _PubMedTaskRepo)
    monkeypatch.setattr(pipeline_mod, "DataRepository", _FakeDataRepo)
    monkeypatch.setattr(pipeline_mod, "LogRepository", _FakeLogRepo)

    async def fake_collect_pubmed_topics(**kwargs) -> dict[str, int]:
        captured_rules.append(kwargs["rules"])
        return {
            "topics": 2,
            "discovered": 6,
            "stored": 4,
            "skipped_hash": 2,
            "failed": 0,
        }

    monkeypatch.setattr(
        pipeline_mod,
        "_collect_pubmed_topics",
        fake_collect_pubmed_topics,
    )

    await pipeline_mod.run_task(1)

    assert captured_rules[0]["topics"][0]["name"] == "脑胶质瘤"
    assert any("PubMed" in message and "入库 4" in message for message in _FakeLogRepo.captured_messages)
