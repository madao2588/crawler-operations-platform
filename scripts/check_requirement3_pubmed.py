from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.engine.clinical_trials import (
    ClinicalTrialsGovClient,
    is_study_relevant_to_topic,
)
from app.engine.pubmed import PubMedClient
from app.services.template_service import NEW_DRUG_SOURCE_TEMPLATES


def _rules_for(template_id: str, crawl_mode: str) -> dict[str, Any]:
    template = next(
        item
        for item in NEW_DRUG_SOURCE_TEMPLATES
        if item["id"] == template_id
    )
    raw_rules = template.get("parser_rules")
    rules = json.loads(str(raw_rules)) if raw_rules else None
    if not isinstance(rules, dict) or rules.get("crawl_mode") != crawl_mode:
        raise ValueError(
            f"{template_id} is missing an executable {crawl_mode} contract"
        )
    return rules


def _source_status(results: list[dict[str, Any]]) -> str:
    successful = sum(item["status"] == "ok" for item in results)
    if successful == len(results) and results:
        return "ok"
    if successful:
        return "partial"
    return "failed"


async def _check_pubmed(*, max_results: int) -> dict[str, Any]:
    rules = _rules_for("pubmed_literature", "pubmed")
    client = PubMedClient()
    results: list[dict[str, Any]] = []
    for raw_topic in rules["topics"]:
        topic = str(raw_topic["name"])
        query = str(raw_topic["query"])
        result: dict[str, Any] = {
            "topic": topic,
            "status": "failed",
            "count": 0,
            "sample": None,
            "error": None,
        }
        try:
            articles = await client.fetch_topic(
                topic=topic,
                query=query,
                max_results=max_results,
                lookback_days=int(rules["lookback_days"]),
            )
            result["count"] = len(articles)
            if articles:
                first = articles[0]
                result["sample"] = {
                    "pmid": first.pmid,
                    "title": first.title,
                    "published_at": (
                        first.published_at.isoformat()
                        if first.published_at is not None
                        else None
                    ),
                    "development_stage": first.development_stage,
                    "evidence_level": first.evidence_level,
                    "targets": first.targets,
                    "trial_ids": first.trial_ids,
                    "source_url": first.source_url,
                }
                result["status"] = "ok"
            else:
                result["error"] = "official API returned no records for the configured lookback"
        except Exception as exc:  # noqa: BLE001 - report each source independently
            result["error"] = str(exc)
        results.append(result)

    return {
        "source": "PubMed E-utilities",
        "status": _source_status(results),
        "topics": results,
    }


async def _check_clinical_trials(*, max_results: int) -> dict[str, Any]:
    rules = _rules_for("clinical_trials_competitor", "clinical_trials")
    client = ClinicalTrialsGovClient()
    results: list[dict[str, Any]] = []
    for raw_topic in rules["topics"]:
        topic = str(raw_topic["name"])
        query = str(raw_topic.get("query") or "").strip() or None
        condition_query = (
            str(raw_topic.get("condition_query") or "").strip() or None
        )
        intervention_type = (
            str(raw_topic.get("intervention_type") or "").strip() or None
        )
        result: dict[str, Any] = {
            "topic": topic,
            "status": "failed",
            "count": 0,
            "sample": None,
            "error": None,
        }
        try:
            page = await client.search_studies(
                query_term=query,
                query_condition=condition_query,
                intervention_type=intervention_type,
                page_size=max_results,
            )
            relevant_studies = [
                study
                for study in page.studies
                if is_study_relevant_to_topic(study, topic)
            ]
            result["count"] = len(relevant_studies)
            if relevant_studies:
                first = relevant_studies[0]
                result["sample"] = {
                    "nct_id": first.nct_id,
                    "title": first.brief_title,
                    "development_stage": first.phase,
                    "trial_status": first.status,
                    "sponsor": first.sponsor,
                    "drugs": first.drug_assets,
                    "targets": first.targets,
                    "source_url": first.study_url,
                }
                result["status"] = "ok"
            elif page.studies:
                result["error"] = (
                    "official API returned records but no relevant study matched "
                    "the configured topic contract"
                )
            else:
                result["error"] = "official API returned no records"
        except Exception as exc:  # noqa: BLE001 - report each source independently
            result["error"] = str(exc)
        results.append(result)
    return {
        "source": "ClinicalTrials.gov API v2",
        "status": _source_status(results),
        "topics": results,
    }


async def run_check(*, max_results: int) -> dict[str, Any]:
    sources = [
        await _check_pubmed(max_results=max_results),
        await _check_clinical_trials(max_results=max_results),
    ]
    source_statuses = [str(source["status"]) for source in sources]
    if source_statuses and all(status == "ok" for status in source_statuses):
        status = "ok"
    elif any(status in {"ok", "partial"} for status in source_statuses):
        status = "partial"
    else:
        status = "failed"
    return {
        "requirement": 3,
        "status": status,
        "sources": sources,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only live check for requirement 3 official PubMed and "
            "ClinicalTrials.gov topic queries."
        )
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=3,
        help="Maximum records fetched per topic and official source (default: 3).",
    )
    args = parser.parse_args()
    result = asyncio.run(
        run_check(max_results=max(1, min(args.max_results, 10)))
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] in {"ok", "partial"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
