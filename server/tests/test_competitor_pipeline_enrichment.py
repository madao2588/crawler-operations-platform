from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import app.engine.pipeline as pipeline_mod
from app.engine.clinical_trials import ClinicalTrialStudy
from app.engine.pubmed import PubMedArticle


class _RecordingDataRepo:
    def __init__(self) -> None:
        self.created: dict[str, object] | None = None
        self.snapshot_path: str | None = None

    async def get_by_source_url(self, _source_url: str):
        return None

    async def get_by_hash(self, _content_hash: str):
        return None

    async def create(self, **kwargs):
        self.created = kwargs
        return SimpleNamespace(id=42)

    async def update_snapshot_path(self, *, data, snapshot_path: str):
        assert data.id == 42
        self.snapshot_path = snapshot_path


class _RecordingLogRepo:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def create(self, **kwargs) -> None:
        message = kwargs.get("message")
        if isinstance(message, str):
            self.messages.append(message)


@pytest.mark.asyncio
async def test_pubmed_enrichment_is_persisted_and_rendered(monkeypatch) -> None:
    data_repo = _RecordingDataRepo()
    log_repo = _RecordingLogRepo()
    monkeypatch.setattr(pipeline_mod, "save_snapshot", lambda **_kwargs: "snapshot.html")
    article = PubMedArticle(
        pmid="12345678",
        topic="脑胶质瘤",
        title="Phase II EGFR inhibitor study",
        abstract="A recruiting study in China.",
        journal="Example Journal",
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
        doi="10.1000/example",
        authors=["A. Author"],
        organizations=["Example Therapeutics"],
        drugs=["EX-101"],
        keywords=["glioblastoma"],
        publication_types=["Clinical Trial"],
        development_stage="临床Ⅱ期",
        evidence_level="临床试验证据",
        mesh_terms=["Glioblastoma", "Drug Therapy"],
        targets=["EGFR"],
        sponsor_hints=["Example Therapeutics"],
        trial_ids=["NCT12345678"],
        trial_status="recruiting",
        countries=["China"],
        development_stage_evidence="Phase II",
        development_stage_confidence="high",
    )

    outcome = await pipeline_mod._store_pubmed_article(
        task_id=1,
        run_id="run1",
        article=article,
        log_repo=log_repo,
        data_repo=data_repo,
    )

    assert outcome == "stored"
    assert data_repo.created is not None
    metadata = json.loads(str(data_repo.created["metadata_json"]))
    assert metadata["mesh_terms"] == ["Glioblastoma", "Drug Therapy"]
    assert metadata["targets"] == ["EGFR"]
    assert metadata["sponsor_hints"] == ["Example Therapeutics"]
    assert metadata["trial_ids"] == ["NCT12345678"]
    assert metadata["trial_status"] == "recruiting"
    assert metadata["countries"] == ["China"]
    assert metadata["development_stage_evidence"] == "Phase II"
    assert metadata["development_stage_confidence"] == "high"
    content_text = str(data_repo.created["content_text"])
    assert "靶点：EGFR" in content_text
    assert "临床试验编号：NCT12345678" in content_text


@pytest.mark.asyncio
async def test_clinical_trial_is_stored_as_competitor_intelligence(monkeypatch) -> None:
    data_repo = _RecordingDataRepo()
    log_repo = _RecordingLogRepo()
    monkeypatch.setattr(pipeline_mod, "save_snapshot", lambda **_kwargs: "trial.html")
    study = ClinicalTrialStudy(
        nct_id="NCT87654321",
        brief_title="A phase 2 trial of EX-101 in glioblastoma",
        official_title="Official EX-101 trial title",
        brief_summary="Recruiting phase 2 trial.",
        phase="Phase 2",
        status="recruiting",
        sponsor="Example Therapeutics",
        collaborators=["Example University"],
        conditions=["Glioblastoma"],
        interventions=["EX-101"],
        drug_assets=["EX-101"],
        targets=["EGFR"],
        trial_ids=["NCT87654321"],
        countries=["China", "United States"],
        keywords=["glioma"],
        study_url="https://clinicaltrials.gov/study/NCT87654321",
    )

    outcome = await pipeline_mod._store_clinical_trial(
        task_id=2,
        run_id="run2",
        topic="脑胶质瘤",
        study=study,
        log_repo=log_repo,
        data_repo=data_repo,
    )

    assert outcome == "stored"
    assert data_repo.created is not None
    assert data_repo.created["category"] == "竞品信息"
    metadata = json.loads(str(data_repo.created["metadata_json"]))
    assert metadata["source"] == "ClinicalTrials.gov"
    assert metadata["external_id"] == "NCT87654321"
    assert metadata["drugs"] == ["EX-101"]
    assert metadata["development_stage"] == "Phase 2"
    assert metadata["trial_status"] == "recruiting"
    assert metadata["sponsor"] == "Example Therapeutics"
    assert metadata["countries"] == ["China", "United States"]


@pytest.mark.asyncio
async def test_clinical_trials_collector_rejects_irrelevant_api_results(
    monkeypatch,
) -> None:
    irrelevant_study = ClinicalTrialStudy(
        nct_id="NCT99999999",
        brief_title="Breast cancer treatment study",
        official_title="Randomized study in breast cancer",
        brief_summary="A drug intervention for breast cancer.",
        phase="Phase 2",
        status="recruiting",
        sponsor="Example Therapeutics",
        collaborators=[],
        conditions=["Breast Cancer"],
        interventions=["EX-999"],
        drug_assets=["EX-999"],
        targets=[],
        trial_ids=["NCT99999999"],
        countries=["China"],
        keywords=["breast neoplasm"],
        study_url="https://clinicaltrials.gov/study/NCT99999999",
    )

    class _IrrelevantClient:
        async def search_studies(self, **_kwargs):
            return SimpleNamespace(studies=[irrelevant_study])

    data_repo = _RecordingDataRepo()
    log_repo = _RecordingLogRepo()
    monkeypatch.setattr(pipeline_mod, "ClinicalTrialsGovClient", _IrrelevantClient)

    with pytest.raises(ValueError, match="no relevant studies"):
        await pipeline_mod._collect_clinical_trials_topics(
            task_id=3,
            run_id="run-irrelevant",
            rules={
                "topics": [
                    {
                        "name": "降尿酸药物",
                        "condition_query": "Hyperuricemia OR Gout",
                        "intervention_type": "DRUG",
                    }
                ]
            },
            log_repo=log_repo,
            data_repo=data_repo,
        )

    assert data_repo.created is None
    assert any("no relevant studies" in message for message in log_repo.messages)


class _ClinicalTrialsTaskRepo:
    def __init__(self, _session) -> None:
        self.task = SimpleNamespace(
            id=3,
            start_url="https://clinicaltrials.gov/search",
            parser_rules=json.dumps(
                {
                    "crawl_mode": "clinical_trials",
                    "max_results_per_topic": 20,
                    "topics": [
                        {"name": "脑胶质瘤", "query": "glioma"},
                        {"name": "降尿酸药物", "query": "hyperuricemia"},
                    ],
                },
                ensure_ascii=False,
            ),
        )

    async def get_by_id(self, task_id: int):
        return self.task if task_id == 3 else None


class _FakeSessionCtx:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        _ = (exc_type, exc, tb)
        return False


class _TaskLogRepo(_RecordingLogRepo):
    captured_messages: list[str] = []

    def __init__(self, _session) -> None:
        super().__init__()

    async def create(self, **kwargs) -> None:
        await super().create(**kwargs)
        self.captured_messages.extend(self.messages[-1:])


class _TaskDataRepo:
    def __init__(self, _session) -> None:
        pass


@pytest.mark.asyncio
async def test_clinical_trials_mode_uses_structured_collector_and_emits_summary(
    monkeypatch,
) -> None:
    _TaskLogRepo.captured_messages.clear()
    captured_rules: list[dict[str, object]] = []
    monkeypatch.setattr(pipeline_mod, "AsyncSessionLocal", lambda: _FakeSessionCtx())
    monkeypatch.setattr(pipeline_mod, "TaskRepository", _ClinicalTrialsTaskRepo)
    monkeypatch.setattr(pipeline_mod, "DataRepository", _TaskDataRepo)
    monkeypatch.setattr(pipeline_mod, "LogRepository", _TaskLogRepo)

    async def fake_collect_clinical_trials_topics(**kwargs) -> dict[str, int]:
        captured_rules.append(kwargs["rules"])
        return {
            "topics": 2,
            "discovered": 8,
            "stored": 6,
            "skipped_hash": 2,
            "failed": 0,
        }

    monkeypatch.setattr(
        pipeline_mod,
        "_collect_clinical_trials_topics",
        fake_collect_clinical_trials_topics,
    )

    outcome = await pipeline_mod.run_task(3)

    assert outcome == "success"
    assert captured_rules[0]["topics"][0]["name"] == "脑胶质瘤"
    assert any(
        "ClinicalTrials.gov" in message and "入库 6" in message
        for message in _TaskLogRepo.captured_messages
    )
