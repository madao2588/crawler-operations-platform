from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import scripts.check_requirement3_pubmed as healthcheck


class _PubMedClient:
    async def fetch_topic(self, **_kwargs):
        return [
            SimpleNamespace(
                pmid="12345678",
                title="Example PubMed trial",
                published_at=datetime(2026, 7, 1, tzinfo=UTC),
                development_stage="临床Ⅱ期",
                evidence_level="临床试验证据",
                targets=["EGFR"],
                trial_ids=["NCT12345678"],
                source_url="https://pubmed.ncbi.nlm.nih.gov/12345678/",
            )
        ]


class _ClinicalTrialsClient:
    async def search_studies(self, **kwargs):
        is_glioma = "Glioma" in str(kwargs.get("query_condition"))
        return SimpleNamespace(
            studies=[
                SimpleNamespace(
                    nct_id="NCT12345678",
                    brief_title=(
                        "Example glioblastoma registered trial"
                        if is_glioma
                        else "Example hyperuricemia registered trial"
                    ),
                    official_title="",
                    brief_summary="Drug intervention study",
                    phase="Phase 2",
                    status="recruiting",
                    sponsor="Example Therapeutics",
                    collaborators=[],
                    conditions=["Glioblastoma" if is_glioma else "Hyperuricemia"],
                    interventions=["EX-101"],
                    drug_assets=["EX-101"],
                    targets=["EGFR"],
                    trial_ids=["NCT12345678"],
                    countries=["China"],
                    keywords=[],
                    study_url="https://clinicaltrials.gov/study/NCT12345678",
                )
            ]
        )


@pytest.mark.asyncio
async def test_requirement3_healthcheck_covers_pubmed_and_clinical_trials(
    monkeypatch,
) -> None:
    monkeypatch.setattr(healthcheck, "PubMedClient", _PubMedClient)
    monkeypatch.setattr(
        healthcheck,
        "ClinicalTrialsGovClient",
        _ClinicalTrialsClient,
    )

    result = await healthcheck.run_check(max_results=2)

    assert result["status"] == "ok"
    assert {source["source"] for source in result["sources"]} == {
        "PubMed E-utilities",
        "ClinicalTrials.gov API v2",
    }
    pubmed = result["sources"][0]
    clinical = result["sources"][1]
    assert pubmed["topics"][0]["sample"]["targets"] == ["EGFR"]
    assert clinical["topics"][0]["sample"]["trial_status"] == "recruiting"
    assert clinical["topics"][0]["sample"]["drugs"] == ["EX-101"]


class _FailingClinicalTrialsClient:
    async def search_studies(self, **_kwargs):
        raise TimeoutError("clinical trials timed out")


@pytest.mark.asyncio
async def test_requirement3_healthcheck_reports_partial_when_one_official_source_fails(
    monkeypatch,
) -> None:
    monkeypatch.setattr(healthcheck, "PubMedClient", _PubMedClient)
    monkeypatch.setattr(
        healthcheck,
        "ClinicalTrialsGovClient",
        _FailingClinicalTrialsClient,
    )

    result = await healthcheck.run_check(max_results=1)

    assert result["status"] == "partial"
    assert result["sources"][0]["status"] == "ok"
    assert result["sources"][1]["status"] == "failed"


class _IrrelevantClinicalTrialsClient:
    async def search_studies(self, **_kwargs):
        return SimpleNamespace(
            studies=[
                SimpleNamespace(
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
            ]
        )


@pytest.mark.asyncio
async def test_requirement3_healthcheck_rejects_irrelevant_clinical_trial_records(
    monkeypatch,
) -> None:
    monkeypatch.setattr(healthcheck, "PubMedClient", _PubMedClient)
    monkeypatch.setattr(
        healthcheck,
        "ClinicalTrialsGovClient",
        _IrrelevantClinicalTrialsClient,
    )

    result = await healthcheck.run_check(max_results=1)

    clinical = result["sources"][1]
    assert result["status"] == "partial"
    assert clinical["status"] == "failed"
    assert clinical["topics"][0]["count"] == 0
    assert "no relevant study matched" in clinical["topics"][0]["error"]
