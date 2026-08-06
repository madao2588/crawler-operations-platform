from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.engine.downloader import fetch_static
from app.engine.meeting import (
    extract_meeting_table_records,
    is_valid_registration_url,
)
from app.engine.parser import (
    detail_rules_json,
    extract_list_follow_items,
    fetch_timeout_seconds,
    looks_like_anti_bot_challenge,
)
from app.engine.pipeline import extract_meeting_metadata
from app.services.template_service import NEW_DRUG_SOURCE_TEMPLATES

TEMPLATE_IDS = {
    "dxy_pharmacy_meetings",
    "cpa_association",
    "bioon_meetings",
    "cphi_china_events",
}


def _templates() -> dict[str, dict[str, Any]]:
    return {
        str(item["id"]): item
        for item in NEW_DRUG_SOURCE_TEMPLATES
        if item["id"] in TEMPLATE_IDS
    }


async def _fetch(url: str, rules: dict[str, object]) -> str:
    return await fetch_static(
        url,
        timeout=fetch_timeout_seconds(rules, 45.0),
    )


async def _probe_list_follow(
    template: dict[str, Any],
    *,
    expected_status: str,
) -> dict[str, Any]:
    rules = json.loads(str(template["parser_rules"]))
    result: dict[str, Any] = {
        "source_id": template["id"],
        "label": template["label"],
        "status": "failed",
        "enabled": template["enabled"],
        "matched_items": 0,
        "sample_title": None,
        "sample_url": None,
        "metadata": None,
        "error": None,
    }
    try:
        list_html = await _fetch(str(template["start_url"]), rules)
        if looks_like_anti_bot_challenge(list_html, rules):
            result["status"] = "blocked"
            result["error"] = str(
                rules.get("disabled_reason") or "anti-bot challenge detected"
            )
            return result
        items = extract_list_follow_items(
            list_html,
            str(template["start_url"]),
            rules,
            url_cap=20,
        )
        result["matched_items"] = len(items)
        if not items:
            raise ValueError("list contract matched zero detail links")

        sample = items[0]
        detail_html = await _fetch(sample["url"], rules)
        detail_contract = json.loads(detail_rules_json(rules) or "{}")
        fallback_title = sample.get("title")
        metadata = extract_meeting_metadata(
            detail_html,
            source_url=sample["url"],
            rules={**rules, **detail_contract},
            fallback_title=fallback_title,
        )
        result.update(
            {
                "status": _normalized_status(
                    expected_status,
                    metadata=metadata,
                    sample_url=sample["url"],
                ),
                "sample_title": (
                    metadata.get("meeting_name")
                    if isinstance(metadata, dict)
                    else fallback_title
                ),
                "sample_url": sample["url"],
                "metadata": metadata,
                "error": _status_error(
                    metadata=metadata,
                    sample_url=sample["url"],
                ),
            }
        )
    except Exception as exc:  # noqa: BLE001 - each external source is isolated
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


async def _probe_cphi(template: dict[str, Any]) -> dict[str, Any]:
    rules = json.loads(str(template["parser_rules"]))
    result: dict[str, Any] = {
        "source_id": template["id"],
        "label": template["label"],
        "status": "failed",
        "enabled": template["enabled"],
        "matched_items": 0,
        "sample_title": None,
        "sample_url": None,
        "metadata": None,
        "error": None,
    }
    try:
        page_html = await _fetch(str(template["start_url"]), rules)
        records = extract_meeting_table_records(
            page_html,
            source_url=str(template["start_url"]),
            rules=rules,
        )
        if not records:
            raise ValueError("meeting table matched zero records")
        sample = records[0]
        result.update(
            {
                "status": "ok",
                "matched_items": len(records),
                "sample_title": sample.title,
                "sample_url": sample.source_url,
                "metadata": sample.metadata,
            }
        )
    except Exception as exc:  # noqa: BLE001 - isolate external source failures
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


async def _run() -> list[dict[str, Any]]:
    templates = _templates()
    cpa, dxy, bioon, cphi = await asyncio.gather(
        _probe_list_follow(templates["cpa_association"], expected_status="ok"),
        _probe_list_follow(templates["dxy_pharmacy_meetings"], expected_status="stale"),
        _probe_list_follow(templates["bioon_meetings"], expected_status="intermittent"),
        _probe_cphi(templates["cphi_china_events"]),
    )
    return [cpa, cphi, dxy, bioon]


def _normalized_status(
    expected_status: str,
    *,
    metadata: object,
    sample_url: str,
) -> str:
    if not isinstance(metadata, dict):
        return "partial"
    if _invalid_registration_url(metadata, sample_url):
        return "partial"
    return expected_status


def _status_error(*, metadata: object, sample_url: str) -> str | None:
    if not isinstance(metadata, dict):
        return "meeting metadata missing"
    invalid_registration_url = _invalid_registration_url(metadata, sample_url)
    if invalid_registration_url:
        return f"invalid registration_url: {invalid_registration_url}"
    return None


def _invalid_registration_url(
    metadata: dict[str, Any],
    sample_url: str,
) -> str | None:
    registration_url = str(metadata.get("registration_url") or "").strip()
    if not registration_url:
        return None
    if is_valid_registration_url(
        registration_url,
        source_url=sample_url,
        context_text="报名入口",
    ):
        return None
    return registration_url


def _overall_status(results: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("status") or "partial") for item in results}
    if not statuses or statuses == {"ok"}:
        return "ok"
    if "partial" not in statuses and statuses <= {"ok", "stale", "intermittent"}:
        return "operational_with_constraints"
    return "partial"


def _status_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts = {
        "ok": 0,
        "intermittent": 0,
        "stale": 0,
        "partial": 0,
    }
    for item in results:
        status = str(item.get("status") or "partial")
        if status in counts:
            counts[status] += 1
        elif status == "blocked":
            counts["intermittent"] += 1
        else:
            counts["partial"] += 1
    return counts


def main() -> int:
    results = asyncio.run(_run())
    output = {
        "overall": _overall_status(results),
        "counts": _status_counts(results),
        "sources": results,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return (
        0
        if output["overall"] in {"ok", "operational_with_constraints"}
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
