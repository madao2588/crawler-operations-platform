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

from app.engine.cleaner import clean_content
from app.engine.downloader import (
    FallbackFetchError,
    classify_fetch_exception,
    fetch_dynamic,
    fetch_static,
)
from app.engine.parser import (
    detail_rules_json,
    extract_embedded_content_url,
    extract_embedded_json_content,
    extract_list_follow_items,
    fetch_timeout_seconds,
    parse_with_rules,
    resolve_list_page_urls,
)
from app.services.template_service import (
    NEW_DRUG_SOURCE_TEMPLATES,
    PROJECT_DECLARATION_ENABLED_TEMPLATE_IDS,
)
from app.utils.notice import project_notice_kind
from app.utils.published_at import parse_published_at

PROJECT_SIGNAL_LABELS = ("申报通知", "结果公示", "其他项目线索")


async def _fetch(url: str, rules: dict[str, object]) -> tuple[str, str]:
    timeout = fetch_timeout_seconds(rules, 45.0)
    wait_for_selector_raw = rules.get("dynamic_wait_selector")
    wait_for_selector = (
        wait_for_selector_raw.strip()
        if isinstance(wait_for_selector_raw, str) and wait_for_selector_raw.strip()
        else None
    )
    if rules.get("force_dynamic_fetch") is True:
        return (
            await fetch_dynamic(
                url,
                timeout=timeout,
                wait_for_selector=wait_for_selector,
            ),
            "dynamic",
        )
    try:
        return await fetch_static(url, timeout=timeout), "static"
    except Exception as static_exc:  # noqa: BLE001 - any static failure should exercise the dynamic fallback
        try:
            return (
                await fetch_dynamic(
                    url,
                    timeout=timeout,
                    wait_for_selector=wait_for_selector,
                ),
                "dynamic",
            )
        except Exception as dynamic_exc:
            raise FallbackFetchError(
                static_exc=static_exc,
                dynamic_exc=dynamic_exc,
            ) from dynamic_exc


async def probe_source(template: dict[str, Any]) -> dict[str, Any]:
    source_id = str(template["id"])
    result: dict[str, Any] = {
        "source_id": source_id,
        "label": str(template["label"]),
        "status": "failed",
        "list_url": None,
        "list_pages": [],
        "fetch_mode": None,
        "matched_items": 0,
        "signal_counts": {label: 0 for label in PROJECT_SIGNAL_LABELS},
        "signal_samples": {label: [] for label in PROJECT_SIGNAL_LABELS},
        "detail_url": None,
        "detail_title": None,
        "published_at": None,
        "content_length": 0,
        "failure_kind": None,
        "error": None,
    }
    try:
        rules = json.loads(str(template["parser_rules"]))
        if not isinstance(rules, dict) or rules.get("crawl_mode") != "list_follow":
            raise ValueError("source is missing a list_follow contract")

        discovered: list[dict[str, str]] = []
        seen_detail_urls: set[str] = set()
        list_page_failures = 0
        for list_url in resolve_list_page_urls(str(template["start_url"]), rules):
            try:
                list_html, fetch_mode = await _fetch(list_url, rules)
                page_items = extract_list_follow_items(
                    list_html,
                    list_url,
                    rules,
                    url_cap=20,
                )
                for item in page_items:
                    if item["url"] not in seen_detail_urls:
                        seen_detail_urls.add(item["url"])
                        discovered.append(item)
                result["list_pages"].append(
                    {
                        "url": list_url,
                        "fetch_mode": fetch_mode,
                        "matched_items": len(page_items),
                        "error": None,
                    }
                )
                if not page_items:
                    list_page_failures += 1
            except Exception as exc:  # noqa: BLE001 - report list pages independently
                list_page_failures += 1
                result["list_pages"].append(
                    {
                        "url": list_url,
                        "fetch_mode": None,
                        "matched_items": 0,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
                continue
            result["list_url"] = list_url
            result["fetch_mode"] = fetch_mode
        if not discovered:
            raise ValueError("list contract matched zero detail links")

        for item in discovered:
            title = str(item.get("title") or "").strip()
            signal = project_notice_kind(
                [title],
                metadata={"kind": "project_notice"},
            )
            result["signal_counts"][signal] += 1
            samples = result["signal_samples"][signal]
            if title and len(samples) < 2:
                samples.append(title)

        detail = discovered[0]
        detail_url = detail["url"]
        detail_html, detail_fetch_mode = await _fetch(detail_url, rules)
        raw_detail_rules = detail_rules_json(rules)
        detail_rules = json.loads(raw_detail_rules) if raw_detail_rules else {}
        parsed = parse_with_rules(detail_html, detail_rules)
        embedded_selector = rules.get("embedded_content_url")
        embedded_assignment = rules.get("embedded_content_json_assignment")
        embedded_content_path = rules.get("embedded_content_json_path")
        embedded_title_path = rules.get("embedded_content_title_path")
        if all(
            isinstance(value, str) and value.strip()
            for value in (
                embedded_selector,
                embedded_assignment,
                embedded_content_path,
            )
        ):
            embedded_url = extract_embedded_content_url(
                detail_html,
                detail_url,
                embedded_selector,
            )
            if embedded_url is not None:
                embedded_html, embedded_fetch_mode = await _fetch(embedded_url, rules)
                embedded = extract_embedded_json_content(
                    embedded_html,
                    assignment=embedded_assignment,
                    content_path=embedded_content_path,
                    title_path=(
                        embedded_title_path
                        if isinstance(embedded_title_path, str)
                        else None
                    ),
                )
                if embedded is None:
                    raise ValueError(
                        f"embedded content contract did not match {embedded_url}"
                    )
                parsed["content_html"] = embedded["content_html"]
                if embedded.get("title"):
                    parsed["title"] = embedded["title"]
                detail_fetch_mode = f"{detail_fetch_mode}+{embedded_fetch_mode}"
        title = (
            detail.get("title")
            if rules.get("prefer_list_title") is True and detail.get("title")
            else parsed.get("title") or detail.get("title")
        )
        cleaned = clean_content(parsed.get("content_html"))
        published_at = parse_published_at(parsed.get("published_at"))

        result.update(
            {
                "status": (
                    "ok"
                    if title
                    and cleaned["content_text"]
                    and published_at
                    and list_page_failures == 0
                    else "degraded"
                ),
                "fetch_mode": f"{result['fetch_mode']}->{detail_fetch_mode}",
                "matched_items": len(discovered),
                "detail_url": detail_url,
                "detail_title": title,
                "published_at": published_at.isoformat() if published_at else None,
                "content_length": len(cleaned["content_text"]),
            }
        )
        if result["status"] == "degraded":
            result["failure_kind"] = "parse_drift"
            result["error"] = (
                "one or more list pages failed, or the detail contract did not "
                "return title, content, and published_at"
            )
    except Exception as exc:  # noqa: BLE001 - isolate each external source in the report
        result["failure_kind"] = _classify_failure(exc, result["list_pages"])
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def _classify_failure(
    exc: Exception,
    list_pages: object,
) -> str:
    classified = classify_fetch_exception(exc)
    if classified is not None:
        return classified

    page_errors: list[str] = []
    if isinstance(list_pages, list):
        for page in list_pages:
            if isinstance(page, dict) and page.get("error"):
                page_errors.append(str(page["error"]))
    page_error_classification = _classify_failure_text(" ".join(page_errors))
    if page_error_classification is not None:
        return page_error_classification

    text = " ".join([type(exc).__name__, str(exc), *page_errors]).lower()
    text_classification = _classify_failure_text(text)
    if text_classification is not None:
        return text_classification
    return "unknown"


def _classify_failure_text(text: str) -> str | None:
    normalized = text.lower()
    if any(marker in normalized for marker in ("status code 403", "403 forbidden")):
        return "http_403"
    if "status code 429" in normalized:
        return "http_429"
    if (
        "connecterror" in normalized
        or "networkerror" in normalized
        or "connection closed" in normalized
        or "connection reset" in normalized
        or "err_connection_closed" in normalized
        or "name or service not known" in normalized
        or "nodename nor servname" in normalized
        or "network is unreachable" in normalized
        or "tls" in normalized
        or "ssl" in normalized
        or "handshake" in normalized
    ):
        return "network_unreachable"
    if "timeout" in normalized or "timed out" in normalized:
        return "timeout"
    if "matched zero detail links" in text:
        return "parse_drift"
    if (
        "httpstatuserror" in normalized
        or "err_http_response_code_failure" in normalized
        or "status code" in normalized
    ):
        return "http_rejected"
    return None


async def _run(source_ids: set[str] | None) -> list[dict[str, Any]]:
    templates = [
        item
        for item in NEW_DRUG_SOURCE_TEMPLATES
        if item["id"] in PROJECT_DECLARATION_ENABLED_TEMPLATE_IDS
        and (source_ids is None or item["id"] in source_ids)
    ]
    semaphore = asyncio.Semaphore(3)

    async def limited_probe(template: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            return await probe_source(template)

    return await asyncio.gather(*(limited_probe(template) for template in templates))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only live health check for Requirement 1 government sources.",
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        help="Probe only this fixed source id; may be repeated.",
    )
    args = parser.parse_args()
    results = asyncio.run(_run(set(args.sources) if args.sources else None))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if results and all(item["status"] == "ok" for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
