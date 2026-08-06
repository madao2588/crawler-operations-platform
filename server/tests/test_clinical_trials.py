from urllib.parse import parse_qs, urlparse

import pytest

from app.engine.clinical_trials import (
    ClinicalTrialsGovClient,
    is_study_relevant_to_topic,
    parse_clinical_trial_study,
)


SAMPLE_STUDY = {
    "protocolSection": {
        "identificationModule": {
            "nctId": "NCT03926130",
            "briefTitle": "A Study of Mirikizumab (LY3074828) in Participants With Crohn's Disease",
            "officialTitle": "A Phase 3 Study to Evaluate Mirikizumab in Participants With Crohn's Disease",
            "secondaryIdInfos": [
                {"id": "I6T-MC-AMAM", "type": "OTHER", "domain": "Eli Lilly and Company"},
                {"id": "2018-004614-18", "type": "EUDRACT_NUMBER"},
            ],
        },
        "statusModule": {
            "overallStatus": "COMPLETED",
        },
        "sponsorCollaboratorsModule": {
            "leadSponsor": {"name": "Eli Lilly and Company", "class": "INDUSTRY"},
            "collaborators": [{"name": "Incyte Corporation", "class": "INDUSTRY"}],
        },
        "descriptionModule": {
            "briefSummary": "Mirikizumab is being evaluated in a phase 3 study of Crohn's disease.",
        },
        "conditionsModule": {
            "conditions": ["Crohn's Disease"],
            "keywords": ["IL23", "biologic"],
        },
        "designModule": {
            "phases": ["PHASE3"],
        },
        "armsInterventionsModule": {
            "interventions": [
                {
                    "type": "DRUG",
                    "name": "Mirikizumab",
                    "otherNames": ["LY3074828"],
                },
                {
                    "type": "DRUG",
                    "name": "Ustekinumab",
                },
            ]
        },
        "contactsLocationsModule": {
            "locations": [
                {"country": "United States"},
                {"country": "Canada"},
                {"country": "United States"},
            ]
        },
    }
}


def test_parse_clinical_trial_study_extracts_requirement3_contract() -> None:
    study = parse_clinical_trial_study(SAMPLE_STUDY)

    assert study.nct_id == "NCT03926130"
    assert study.brief_title.startswith("A Study of Mirikizumab")
    assert study.phase == "Phase 3"
    assert study.status == "completed"
    assert study.sponsor == "Eli Lilly and Company"
    assert study.collaborators == ["Incyte Corporation"]
    assert study.conditions == ["Crohn's Disease"]
    assert study.interventions == ["Mirikizumab", "Ustekinumab"]
    assert study.drug_assets == ["Mirikizumab", "LY3074828", "Ustekinumab"]
    assert study.targets == ["IL23"]
    assert study.trial_ids == ["NCT03926130", "2018-004614-18"]
    assert study.countries == ["United States", "Canada"]
    assert study.study_url == "https://clinicaltrials.gov/study/NCT03926130"


def test_parse_clinical_trial_study_splits_semicolon_delimited_drug_assets() -> None:
    study_payload = {
        "protocolSection": {
            "identificationModule": {"nctId": "NCT00000001", "briefTitle": "Drug trial"},
            "armsInterventionsModule": {
                "interventions": [
                    {
                        "type": "DRUG",
                        "name": "repaglinide; midazolam; SHR4640",
                        "otherNames": ["SHR4640; SHR4640 placebo"],
                    }
                ]
            },
        }
    }

    study = parse_clinical_trial_study(study_payload)

    assert study.drug_assets == [
        "repaglinide",
        "midazolam",
        "SHR4640",
        "SHR4640 placebo",
    ]


def test_clinical_trial_topic_relevance_rejects_unrelated_study() -> None:
    study = parse_clinical_trial_study(SAMPLE_STUDY)

    assert is_study_relevant_to_topic(study, "脑胶质瘤") is False
    assert is_study_relevant_to_topic(study, "降尿酸药物") is False


@pytest.mark.parametrize(
    ("topic", "conditions", "summary"),
    [
        ("脑胶质瘤", ["Glioblastoma"], "Drug treatment for malignant glioma."),
        ("降尿酸药物", ["Gout"], "A urate-lowering treatment study."),
        ("降尿酸药物", ["Hyperuricemia"], "Study of serum uric acid reduction."),
    ],
)
def test_clinical_trial_topic_relevance_accepts_required_topics(
    topic: str,
    conditions: list[str],
    summary: str,
) -> None:
    payload = {
        "protocolSection": {
            "identificationModule": {
                "nctId": "NCT00000002",
                "briefTitle": f"Relevant study for {conditions[0]}",
            },
            "descriptionModule": {"briefSummary": summary},
            "conditionsModule": {"conditions": conditions},
            "armsInterventionsModule": {
                "interventions": [{"type": "DRUG", "name": "EX-101"}]
            },
        }
    }

    study = parse_clinical_trial_study(payload)

    assert is_study_relevant_to_topic(study, topic) is True


@pytest.mark.asyncio
async def test_clinical_trials_client_builds_v2_query_and_parses_page() -> None:
    captured_urls: list[str] = []

    async def fake_fetch_json(url: str) -> dict[str, object]:
        captured_urls.append(url)
        return {
            "studies": [SAMPLE_STUDY],
            "nextPageToken": "next-token",
        }

    client = ClinicalTrialsGovClient(fetch_json=fake_fetch_json)
    page = await client.search_studies(query_term="glioblastoma", page_size=1)

    parsed = urlparse(captured_urls[0])
    query = parse_qs(parsed.query)
    assert parsed.path == "/api/v2/studies"
    assert query["query.term"] == ["glioblastoma"]
    assert query["pageSize"] == ["1"]
    assert page.next_page_token == "next-token"
    assert [study.nct_id for study in page.studies] == ["NCT03926130"]


@pytest.mark.asyncio
async def test_clinical_trials_client_scopes_condition_and_drug_type() -> None:
    captured_urls: list[str] = []

    async def fake_fetch_json(url: str) -> dict[str, object]:
        captured_urls.append(url)
        return {"studies": []}

    client = ClinicalTrialsGovClient(fetch_json=fake_fetch_json)
    await client.search_studies(
        query_condition="Hyperuricemia OR Gout",
        intervention_type="DRUG",
        page_size=25,
    )

    query = parse_qs(urlparse(captured_urls[0]).query)
    assert query["query.cond"] == ["Hyperuricemia OR Gout"]
    assert query["filter.advanced"] == ["AREA[InterventionType]DRUG"]
    assert "query.term" not in query
