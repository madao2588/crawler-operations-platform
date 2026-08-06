import asyncio
import html
import json
import traceback
import uuid
from collections import deque
from collections.abc import Mapping
from dataclasses import replace
from datetime import timezone
import re

import httpx
from bs4 import BeautifulSoup

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.engine.cleaner import clean_content
from app.engine.clinical_trials import (
    ClinicalTrialStudy,
    ClinicalTrialsGovClient,
    is_study_relevant_to_topic,
)
from app.engine.downloader import fetch_dynamic, fetch_static
from app.engine.meeting import (
    MeetingRecord,
    extract_meeting_metadata as _extract_meeting_metadata,
    extract_meeting_table_records,
    is_valid_meeting_record,
)
from app.engine.parser import (
    detail_request_delay_seconds,
    detail_retry_count,
    detail_retry_policy,
    detail_retry_sleep_seconds,
    detail_rules_json,
    detail_url_limit,
    extract_embedded_content_url,
    extract_embedded_json_content,
    extract_list_follow_items,
    extract_next_list_page_url,
    anti_bot_block_backoff_seconds,
    anti_bot_block_status_codes,
    anti_bot_retry_on_block,
    looks_like_anti_bot_challenge,
    fetch_cookie_domain_override,
    fetch_http_cookies,
    fetch_http_headers,
    fetch_login_flow,
    fetch_proxy_config,
    fetch_timeout_seconds,
    list_page_fetch_budget,
    list_request_delay_seconds,
    parse_with_readability,
    parse_with_rules,
    resolve_list_page_urls,
    should_retry_detail_failure,
)
from app.engine.pubmed import PubMedArticle, PubMedClient
from app.engine.validator import quality_score
from app.repositories.data_repo import DataRepository
from app.repositories.log_repo import LogRepository
from app.repositories.task_repo import TaskRepository
from app.utils.file import save_snapshot
from app.utils.hash import sha256_text
from app.utils.notice import build_notice_summary, classify_notice_category
from app.utils.published_at import parse_published_at


class AntiBotBlockedError(RuntimeError):
    """Raised when the fetched page appears to be blocked by anti-bot controls."""


def _summary_payload_json(
    *,
    run_id: str,
    mode: str,
    metrics: Mapping[str, object],
) -> str:
    payload = {
        "kind": "run_summary",
        "run_id": run_id,
        "mode": mode,
        "metrics": dict(metrics),
    }
    return json.dumps(payload, ensure_ascii=False)


def extract_meeting_metadata(
    html: str,
    *,
    source_url: str,
    rules: dict[str, object] | None = None,
    fallback_title: str | None = None,
) -> dict[str, object] | None:
    """Return the normalized meeting schema used by the notice detail UI."""
    configured = rules.get("metadata") if isinstance(rules, dict) else None
    if not (
        isinstance(configured, dict)
        and configured.get("kind") == "industry_meeting"
    ):
        return None

    soup = BeautifulSoup(html, "html.parser")
    title = (fallback_title or "").strip()
    if not title:
        article_title = soup.select_one('meta[name="ArticleTitle"]')
        if article_title is not None:
            title = str(article_title.get("content") or "").strip()
    if not title:
        heading = soup.select_one("h1")
        title = heading.get_text(" ", strip=True) if heading else ""

    metadata = _extract_meeting_metadata(html, source_url=source_url)
    text = soup.get_text("\n", strip=True)
    start_date, end_date = _meeting_date_range(
        str(metadata.get("meeting_date") or ""),
        text,
    )
    location = str(metadata.get("location") or "").strip()
    if not location:
        location = _bioon_location(soup)
    organizer = str(metadata.get("organizer") or "").strip() or None
    registration_url = str(metadata.get("registration_url") or "").strip() or None
    deadline = str(metadata.get("registration_deadline") or "").strip() or None

    validation_metadata = dict(metadata)
    if start_date:
        validation_metadata["start_date"] = start_date
    if location:
        validation_metadata["location"] = location
    if not is_valid_meeting_record(title, validation_metadata):
        raise ValueError(
            "industry_meeting detail page lacks a meeting title and time/location"
        )

    normalized: dict[str, object] = {
        "kind": "industry_meeting",
        "meeting_name": title,
        "start_date": start_date,
        "end_date": end_date,
        "location": location or None,
        "organizer": organizer,
        "registration_url": registration_url,
        "deadline": deadline,
    }
    for key in ("meeting_date", "registration_deadline"):
        value = metadata.get(key)
        if value:
            normalized[key] = value
    return normalized


def _meeting_date_range(raw_value: str, page_text: str) -> tuple[str | None, str | None]:
    combined = f"{raw_value}\n{page_text}"
    iso_match = re.search(
        r"(20\d{2})-(\d{1,2})-(\d{1,2})\s*(?:至|到|—|-)\s*"
        r"(20\d{2})-(\d{1,2})-(\d{1,2})",
        combined,
    )
    if iso_match:
        values = [int(value) for value in iso_match.groups()]
        return (
            f"{values[0]:04d}-{values[1]:02d}-{values[2]:02d}",
            f"{values[3]:04d}-{values[4]:02d}-{values[5]:02d}",
        )

    chinese_match = re.search(
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日?\s*(?:至|到|—|-)\s*"
        r"(?:(\d{1,2})月)?(\d{1,2})日",
        combined,
    )
    if chinese_match:
        year, start_month, start_day, end_month, end_day = chinese_match.groups()
        effective_end_month = end_month or start_month
        return (
            f"{int(year):04d}-{int(start_month):02d}-{int(start_day):02d}",
            f"{int(year):04d}-{int(effective_end_month):02d}-{int(end_day):02d}",
        )

    single_match = re.search(
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日",
        combined,
    )
    if single_match:
        year, month, day = (int(value) for value in single_match.groups())
        value = f"{year:04d}-{month:02d}-{day:02d}"
        return value, value
    return None, None


def _bioon_location(soup: BeautifulSoup) -> str:
    node = soup.select_one(".address-time")
    if node is None:
        return ""
    clone = BeautifulSoup(str(node), "html.parser")
    for child in clone.select("span"):
        child.decompose()
    return clone.get_text(" ", strip=True)


async def _collect_and_store_one(
    *,
    task_id: int,
    run_id: str,
    page_url: str,
    parser_rules: str | None,
    log_repo: LogRepository,
    data_repo: DataRepository,
    crawl_rules: dict[str, object] | None = None,
    fallback_title: str | None = None,
) -> str:
    """Download one URL, parse, persist. Returns ``stored`` or ``skipped_hash``.

    Same ``source_url`` is updated only when body content changes. Unchanged
    re-crawls are reported as ``skipped_hash`` so fixed-source monitoring does
    not look like duplicate collection.
    """
    html = await _download_page(
        url=page_url,
        log_repo=log_repo,
        task_id=task_id,
        run_id=run_id,
        crawl_rules=crawl_rules,
    )
    parsed = await _parse_page(
        html,
        parser_rules=parser_rules,
        source_url=page_url,
        log_repo=log_repo,
        task_id=task_id,
        run_id=run_id,
    )
    parsed = await _hydrate_embedded_content(
        parsed=parsed,
        page_html=html,
        page_url=page_url,
        crawl_rules=crawl_rules,
        log_repo=log_repo,
        task_id=task_id,
        run_id=run_id,
    )
    prefer_list_title = bool(
        isinstance(crawl_rules, dict) and crawl_rules.get("prefer_list_title")
    )
    parsed["title"] = _best_title(
        parsed.get("title"),
        fallback_title,
        prefer_fallback=prefer_list_title,
    )
    meeting_metadata = extract_meeting_metadata(
        html,
        source_url=page_url,
        rules=crawl_rules,
        fallback_title=parsed.get("title"),
    )
    if meeting_metadata is not None:
        parsed["title"] = _best_title(
            parsed.get("title"),
            str(meeting_metadata.get("meeting_name") or ""),
        )
        parsed["content_html"] = _meeting_detail_content_html(
            title=str(parsed.get("title") or ""),
            metadata=meeting_metadata,
            original_html=parsed.get("content_html"),
        )
    cleaned = clean_content(parsed["content_html"])
    score = quality_score(parsed.get("title"), cleaned["content_text"])
    configured_category = (
        str(crawl_rules.get("category") or "").strip()
        if isinstance(crawl_rules, dict)
        else ""
    )
    category = configured_category or classify_notice_category(
        [parsed.get("title"), cleaned["content_text"], page_url]
    )
    configured_metadata = (
        crawl_rules.get("metadata") if isinstance(crawl_rules, dict) else None
    )
    if meeting_metadata is not None:
        merged_metadata = (
            dict(configured_metadata)
            if isinstance(configured_metadata, dict)
            else {}
        )
        merged_metadata.update(meeting_metadata)
        configured_metadata = merged_metadata
    metadata_json = (
        json.dumps(configured_metadata, ensure_ascii=False, sort_keys=True)
        if isinstance(configured_metadata, dict)
        else None
    )
    ai_summary = build_notice_summary(cleaned["content_text"])
    published_at = parse_published_at(parsed.get("published_at"))

    if score < 40:
        await log_repo.create(
            level="WARNING",
            task_id=task_id,
            message=(f"[run={run_id}] Task {task_id} produced low quality content: {score} ({page_url})"),
        )

    content_hash = sha256_text(cleaned["content_text"])
    existing = await data_repo.get_by_source_url(page_url)
    if existing is not None:
        if existing.content_hash == content_hash:
            metadata_update: dict[str, object] = dict(
                _unchanged_metadata_update(
                    existing.title,
                    parsed.get("title"),
                    existing.ai_summary,
                    ai_summary,
                    prefer_incoming_title=prefer_list_title,
                )
            )
            existing_published_at = existing.published_at
            if existing_published_at is not None and existing_published_at.tzinfo is None:
                existing_published_at = existing_published_at.replace(tzinfo=timezone.utc)
            if published_at is not None and existing_published_at != published_at:
                metadata_update["published_at"] = published_at
            if metadata_json is not None and getattr(existing, "metadata_json", None) != metadata_json:
                metadata_update["metadata_json"] = metadata_json
            if configured_category and existing.category != category:
                metadata_update["category"] = category
            if metadata_update:
                await data_repo.update_review_metadata(existing, **metadata_update)
            await log_repo.create(
                level="INFO",
                task_id=task_id,
                message=(f"[run={run_id}] Existing URL unchanged for task {task_id}, skipping update ({page_url})"),
            )
            return "skipped_hash"

        stored = await data_repo.update(
            existing,
            task_id=task_id,
            title=parsed.get("title"),
            content_html=cleaned["content_html"],
            content_text=cleaned["content_text"],
            quality_score=score,
            content_hash=content_hash,
            published_at=published_at,
            category=category,
            ai_summary=ai_summary,
            metadata_json=metadata_json,
        )
    else:
        duplicate = await data_repo.get_by_hash(content_hash)
        if duplicate is not None:
            await log_repo.create(
                level="INFO",
                task_id=task_id,
                message=(f"[run={run_id}] Duplicate content detected for task {task_id}, skipping storage ({page_url})"),
            )
            return "skipped_hash"

        stored = await data_repo.create(
            task_id=task_id,
            title=parsed.get("title"),
            content_html=cleaned["content_html"],
            content_text=cleaned["content_text"],
            source_url=page_url,
            snapshot_path=None,
            quality_score=score,
            content_hash=content_hash,
            published_at=published_at,
            category=category,
            ai_summary=ai_summary,
            metadata_json=metadata_json,
        )

    try:
        snapshot_path = save_snapshot(data_id=stored.id, html=html)
        await data_repo.update_snapshot_path(data=stored, snapshot_path=snapshot_path)
    except Exception as exc:
        await log_repo.create(
            level="ERROR",
            task_id=task_id,
            message=f"[run={run_id}] Snapshot save failed for data {stored.id}",
            error_stack=str(exc),
        )

    await log_repo.create(
        level="INFO",
        task_id=task_id,
        message=f"[run={run_id}] Task {task_id} collected data item {stored.id} ({page_url})",
    )
    return "stored"


async def _hydrate_embedded_content(
    *,
    parsed: dict[str, str | None],
    page_html: str,
    page_url: str,
    crawl_rules: dict[str, object] | None,
    log_repo: LogRepository,
    task_id: int,
    run_id: str,
) -> dict[str, str | None]:
    if not isinstance(crawl_rules, dict):
        return parsed
    selector = crawl_rules.get("embedded_content_url")
    assignment = crawl_rules.get("embedded_content_json_assignment")
    content_path = crawl_rules.get("embedded_content_json_path")
    title_path = crawl_rules.get("embedded_content_title_path")
    if not all(
        isinstance(value, str) and value.strip()
        for value in (selector, assignment, content_path)
    ):
        return parsed
    embedded_url = extract_embedded_content_url(page_html, page_url, selector)
    if embedded_url is None:
        return parsed
    embedded_html = await _download_page(
        run_id=run_id,
        task_id=task_id,
        log_repo=log_repo,
        url=embedded_url,
        crawl_rules=crawl_rules,
    )
    embedded = extract_embedded_json_content(
        embedded_html,
        assignment=assignment,
        content_path=content_path,
        title_path=title_path if isinstance(title_path, str) else None,
    )
    if embedded is None:
        raise ValueError(f"embedded content contract did not match {embedded_url}")
    hydrated = dict(parsed)
    hydrated["content_html"] = embedded["content_html"]
    if embedded.get("title"):
        hydrated["title"] = embedded["title"]
    return hydrated


def _meeting_detail_content_html(
    *,
    title: str,
    metadata: Mapping[str, object],
    original_html: str | None,
) -> str:
    start_date = str(metadata.get("start_date") or "").strip()
    end_date = str(metadata.get("end_date") or "").strip()
    if start_date and end_date and end_date != start_date:
        meeting_date = f"{start_date} 至 {end_date}"
    else:
        meeting_date = (
            start_date
            or end_date
            or str(metadata.get("meeting_date") or "").strip()
        )
    rows = [
        ("会议时间", meeting_date),
        ("会议地点", str(metadata.get("location") or "").strip()),
        ("主办方", str(metadata.get("organizer") or "").strip()),
        (
            "报名截止",
            str(
                metadata.get("deadline")
                or metadata.get("registration_deadline")
                or ""
            ).strip(),
        ),
    ]
    table_rows = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>"
        for label, value in rows
        if value
    )
    registration_url = str(metadata.get("registration_url") or "").strip()
    registration = (
        '<p><a href="'
        f'{html.escape(registration_url, quote=True)}'
        '">会议报名 / 官方入口</a></p>'
        if registration_url
        else ""
    )
    original = (
        f'<section class="meeting-original-content">{original_html}</section>'
        if original_html
        else ""
    )
    return (
        '<article class="structured-meeting">'
        f"<h1>{html.escape(title)}</h1>"
        f"<table>{table_rows}</table>"
        f"{registration}"
        f"{original}"
        "</article>"
    )


async def _collect_and_store_one_retrying(
    *,
    task_id: int,
    run_id: str,
    page_url: str,
    parser_rules: str | None,
    log_repo: LogRepository,
    data_repo: DataRepository,
    crawl_rules: dict[str, object] | None,
    fallback_title: str | None = None,
) -> str:
    """Like ``_collect_and_store_one`` with optional retries and same return values."""
    extra = detail_retry_count(crawl_rules)
    total = extra + 1
    policy = detail_retry_policy(crawl_rules)
    last_exc: Exception | None = None
    for attempt in range(total):
        try:
            return await _collect_and_store_one(
                task_id=task_id,
                run_id=run_id,
                page_url=page_url,
                parser_rules=parser_rules,
                log_repo=log_repo,
                data_repo=data_repo,
                crawl_rules=crawl_rules,
                fallback_title=fallback_title,
            )
        except Exception as exc:
            last_exc = exc
            if attempt + 1 >= total:
                break
            retryable = isinstance(exc, AntiBotBlockedError) or should_retry_detail_failure(exc, policy)
            if not retryable:
                await log_repo.create(
                    level="INFO",
                    task_id=task_id,
                    message=(f"[run={run_id}] detail failure not retried (policy={policy}) {page_url}: {exc!s}"),
                )
                break
            wait_sec = detail_retry_sleep_seconds(crawl_rules, attempt)
            await log_repo.create(
                level="WARNING",
                task_id=task_id,
                message=(
                    f"[run={run_id}] detail page failed ({page_url}), "
                    f"sleep {wait_sec:.1f}s then retry "
                    f"{attempt + 2}/{total}: {exc!s}"
                ),
            )
            await asyncio.sleep(wait_sec)
    assert last_exc is not None
    raise last_exc


async def collect_manual_url(
    *,
    task_id: int,
    url: str,
    parser_rules: str | None,
    log_repo: LogRepository,
    data_repo: DataRepository,
) -> dict[str, object]:
    rules = _load_rules(parser_rules)
    if not rules or rules.get("collection_mode") != "manual":
        raise ValueError(f"Task {task_id} is not a manual collection source")

    outcome = await _collect_and_store_one_retrying(
        task_id=task_id,
        run_id=f"manual-{uuid.uuid4().hex[:12]}",
        page_url=url,
        parser_rules=detail_rules_json(rules),
        log_repo=log_repo,
        data_repo=data_repo,
        crawl_rules=rules,
    )
    stored = await data_repo.get_by_source_url(url)
    if stored is None:
        raise RuntimeError(f"Manual collection did not produce a notice for {url}")
    return {
        "status": outcome,
        "notice_id": stored.id,
        "source_url": url,
    }


async def _collect_meeting_table(
    *,
    task_id: int,
    run_id: str,
    start_url: str,
    rules: dict[str, object],
    log_repo: LogRepository,
    data_repo: DataRepository,
) -> dict[str, int]:
    page_html = await _download_page(
        url=start_url,
        log_repo=log_repo,
        task_id=task_id,
        run_id=run_id,
        crawl_rules=rules,
    )
    records = extract_meeting_table_records(
        page_html,
        source_url=start_url,
        rules=rules,
    )
    if not records:
        raise ValueError("meeting_table produced zero meeting records")

    metrics = {
        "discovered": len(records),
        "stored": 0,
        "skipped_hash": 0,
        "failed": 0,
    }
    last_error: Exception | None = None
    for record in records:
        try:
            outcome = await _store_meeting_record(
                task_id=task_id,
                run_id=run_id,
                record=record,
                log_repo=log_repo,
                data_repo=data_repo,
            )
            metrics[outcome] += 1
        except Exception as exc:
            metrics["failed"] += 1
            last_error = exc
            await log_repo.create(
                level="ERROR",
                task_id=task_id,
                message=(
                    f"[run={run_id}] Meeting record failed: "
                    f"{record.title} ({record.source_url})"
                ),
                error_stack=str(exc),
            )
    if metrics["stored"] == 0 and metrics["skipped_hash"] == 0 and last_error:
        raise last_error
    return metrics


async def _store_meeting_record(
    *,
    task_id: int,
    run_id: str,
    record: MeetingRecord,
    log_repo: LogRepository,
    data_repo: DataRepository,
) -> str:
    metadata_json = json.dumps(record.metadata, ensure_ascii=False, sort_keys=True)
    content_hash = sha256_text(
        json.dumps(
            {
                "title": record.title,
                "content": record.content_text,
                "metadata": record.metadata,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    existing = await data_repo.get_by_source_url(record.source_url)
    summary = "；".join(
        value
        for value in (
            record.meeting_date,
            record.location,
            record.organizer,
        )
        if value
    )
    if existing is not None:
        if existing.content_hash == content_hash:
            metadata_update: dict[str, object] = {}
            if getattr(existing, "metadata_json", None) != metadata_json:
                metadata_update["metadata_json"] = metadata_json
            if existing.category != "行业会议":
                metadata_update["category"] = "行业会议"
            if metadata_update:
                await data_repo.update_review_metadata(existing, **metadata_update)
            return "skipped_hash"
        stored = await data_repo.update(
            existing,
            task_id=task_id,
            title=record.title,
            content_html=record.content_html,
            content_text=record.content_text,
            quality_score=85,
            content_hash=content_hash,
            published_at=None,
            category="行业会议",
            ai_summary=summary,
            metadata_json=metadata_json,
        )
    else:
        duplicate = await data_repo.get_by_hash(content_hash)
        if duplicate is not None:
            return "skipped_hash"
        stored = await data_repo.create(
            task_id=task_id,
            title=record.title,
            content_html=record.content_html,
            content_text=record.content_text,
            source_url=record.source_url,
            snapshot_path=None,
            quality_score=85,
            content_hash=content_hash,
            published_at=None,
            category="行业会议",
            ai_summary=summary,
            metadata_json=metadata_json,
        )

    try:
        snapshot_path = save_snapshot(data_id=stored.id, html=record.content_html)
        await data_repo.update_snapshot_path(data=stored, snapshot_path=snapshot_path)
    except Exception as exc:
        await log_repo.create(
            level="ERROR",
            task_id=task_id,
            message=f"[run={run_id}] Meeting snapshot save failed for data {stored.id}",
            error_stack=str(exc),
        )
    await log_repo.create(
        level="INFO",
        task_id=task_id,
        message=(
            f"[run={run_id}] Meeting stored as data item {stored.id}: "
            f"{record.title}"
        ),
    )
    return "stored"


async def _collect_pubmed_topics(
    *,
    task_id: int,
    run_id: str,
    rules: dict[str, object],
    log_repo: LogRepository,
    data_repo: DataRepository,
) -> dict[str, int]:
    raw_topics = rules.get("topics")
    if not isinstance(raw_topics, list):
        raise ValueError("PubMed rules require a topics list")

    topics: list[tuple[str, str]] = []
    for raw_topic in raw_topics:
        if not isinstance(raw_topic, dict):
            continue
        name = str(raw_topic.get("name") or "").strip()
        query = str(raw_topic.get("query") or "").strip()
        if name and query:
            topics.append((name, query))
    if not topics:
        raise ValueError("PubMed rules contain no valid topic queries")

    max_results = _bounded_int(
        rules.get("max_results_per_topic"),
        default=25,
        minimum=1,
        maximum=100,
    )
    lookback_days = _bounded_int(
        rules.get("lookback_days"),
        default=730,
        minimum=1,
        maximum=3650,
    )
    metrics = {
        "topics": len(topics),
        "discovered": 0,
        "stored": 0,
        "skipped_hash": 0,
        "failed": 0,
    }
    client = PubMedClient()
    successful_topics = 0
    last_error: Exception | None = None
    for topic_name, query in topics:
        try:
            articles = await client.fetch_topic(
                topic=topic_name,
                query=query,
                max_results=max_results,
                lookback_days=lookback_days,
            )
            successful_topics += 1
            metrics["discovered"] += len(articles)
        except Exception as exc:
            metrics["failed"] += 1
            last_error = exc
            await log_repo.create(
                level="ERROR",
                task_id=task_id,
                message=f"[run={run_id}] PubMed topic failed: {topic_name}",
                error_stack=str(exc),
            )
            continue

        for article in articles:
            try:
                outcome = await _store_pubmed_article(
                    task_id=task_id,
                    run_id=run_id,
                    article=article,
                    log_repo=log_repo,
                    data_repo=data_repo,
                )
                metrics[outcome] += 1
            except Exception as exc:
                metrics["failed"] += 1
                last_error = exc
                await log_repo.create(
                    level="ERROR",
                    task_id=task_id,
                    message=(
                        f"[run={run_id}] PubMed article failed: "
                        f"{article.topic} PMID {article.pmid}"
                    ),
                    error_stack=str(exc),
                )

    if successful_topics == 0 and last_error is not None:
        raise last_error
    return metrics


async def _store_pubmed_article(
    *,
    task_id: int,
    run_id: str,
    article: PubMedArticle,
    log_repo: LogRepository,
    data_repo: DataRepository,
) -> str:
    existing = await data_repo.get_by_source_url(article.source_url)
    topics = _merge_pubmed_topics(
        getattr(existing, "metadata_json", None),
        article.topic,
    )
    effective_article = replace(article, topic="、".join(topics))
    metadata = {
        "kind": "competitor_intelligence",
        "source": "PubMed",
        "topic": effective_article.topic,
        "topics": topics,
        "external_id": effective_article.pmid,
        "doi": effective_article.doi,
        "journal": effective_article.journal,
        "authors": effective_article.authors,
        "organizations": effective_article.organizations,
        "drugs": effective_article.drugs,
        "publication_types": effective_article.publication_types,
        "development_stage": effective_article.development_stage,
        "evidence_level": effective_article.evidence_level,
        "keywords": effective_article.keywords,
        "mesh_terms": effective_article.mesh_terms,
        "targets": effective_article.targets,
        "sponsor_hints": effective_article.sponsor_hints,
        "trial_ids": effective_article.trial_ids,
        "trial_status": effective_article.trial_status,
        "countries": effective_article.countries,
        "development_stage_evidence": effective_article.development_stage_evidence,
        "development_stage_confidence": effective_article.development_stage_confidence,
    }
    metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    content_text = _pubmed_content_text(effective_article)
    content_html = _pubmed_content_html(effective_article)
    content_hash = sha256_text(
        json.dumps(
            {
                "title": effective_article.title,
                "abstract": effective_article.abstract,
                "metadata": metadata,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    quality = min(
        95,
        60
        + (20 if effective_article.abstract else 0)
        + (5 if effective_article.doi else 0)
        + (5 if effective_article.drugs else 0)
        + (5 if effective_article.organizations else 0),
    )
    summary = effective_article.abstract[:500].strip() or (
        f"{effective_article.topic}；"
        f"{effective_article.development_stage}；"
        f"{effective_article.evidence_level}"
    )
    if existing is not None:
        if existing.content_hash == content_hash:
            metadata_update: dict[str, object] = {}
            if getattr(existing, "metadata_json", None) != metadata_json:
                metadata_update["metadata_json"] = metadata_json
            if existing.category != "竞品信息":
                metadata_update["category"] = "竞品信息"
            existing_published_at = existing.published_at
            if (
                existing_published_at is not None
                and existing_published_at.tzinfo is None
            ):
                existing_published_at = existing_published_at.replace(
                    tzinfo=timezone.utc
                )
            if existing_published_at != effective_article.published_at:
                metadata_update["published_at"] = effective_article.published_at
            if metadata_update:
                await data_repo.update_review_metadata(existing, **metadata_update)
            return "skipped_hash"
        stored = await data_repo.update(
            existing,
            task_id=task_id,
            title=effective_article.title,
            content_html=content_html,
            content_text=content_text,
            quality_score=quality,
            content_hash=content_hash,
            published_at=effective_article.published_at,
            category="竞品信息",
            ai_summary=summary,
            metadata_json=metadata_json,
        )
    else:
        duplicate = await data_repo.get_by_hash(content_hash)
        if duplicate is not None:
            return "skipped_hash"
        stored = await data_repo.create(
            task_id=task_id,
            title=effective_article.title,
            content_html=content_html,
            content_text=content_text,
            source_url=effective_article.source_url,
            snapshot_path=None,
            quality_score=quality,
            content_hash=content_hash,
            published_at=effective_article.published_at,
            category="竞品信息",
            ai_summary=summary,
            metadata_json=metadata_json,
        )

    try:
        snapshot_path = save_snapshot(data_id=stored.id, html=content_html)
        await data_repo.update_snapshot_path(data=stored, snapshot_path=snapshot_path)
    except Exception as exc:
        await log_repo.create(
            level="ERROR",
            task_id=task_id,
            message=f"[run={run_id}] PubMed snapshot save failed for data {stored.id}",
            error_stack=str(exc),
        )

    await log_repo.create(
        level="INFO",
        task_id=task_id,
        message=(
            f"[run={run_id}] PubMed stored {effective_article.topic} "
            f"PMID {effective_article.pmid} as data item {stored.id}"
        ),
    )
    return "stored"


def _merge_pubmed_topics(
    raw_metadata: str | None,
    current_topic: str,
) -> list[str]:
    topics: list[str] = []
    if raw_metadata:
        try:
            metadata = json.loads(raw_metadata)
        except (TypeError, ValueError):
            metadata = None
        if (
            isinstance(metadata, dict)
            and metadata.get("kind") == "competitor_intelligence"
            and metadata.get("source") == "PubMed"
        ):
            raw_topics = metadata.get("topics")
            if isinstance(raw_topics, list):
                topics.extend(
                    str(topic).strip()
                    for topic in raw_topics
                    if str(topic).strip()
                )
            elif isinstance(metadata.get("topic"), str):
                topics.extend(
                    topic.strip()
                    for topic in str(metadata["topic"]).split("、")
                    if topic.strip()
                )
    topic = current_topic.strip()
    if topic and topic not in topics:
        topics.append(topic)
    return topics


def _pubmed_content_text(article: PubMedArticle) -> str:
    fields = [
        ("研究方向", article.topic),
        ("PMID", article.pmid),
        ("DOI", article.doi or "未提供"),
        ("期刊", article.journal or "未提供"),
        ("研发阶段", article.development_stage),
        ("证据等级", article.evidence_level),
        ("文献类型", "；".join(article.publication_types) or "未提供"),
        ("药物/化学物质", "；".join(article.drugs) or "未结构化标注"),
        ("作者", "；".join(article.authors) or "未提供"),
        ("机构", "；".join(article.organizations) or "未提供"),
        ("关键词", "；".join(article.keywords) or "未提供"),
        ("MeSH主题词", "；".join(article.mesh_terms) or "未提供"),
        ("靶点", "；".join(article.targets) or "未结构化标注"),
        ("申办方线索", "；".join(article.sponsor_hints) or "未提供"),
        ("临床试验编号", "；".join(article.trial_ids) or "未提供"),
        ("试验状态", article.trial_status or "未提供"),
        ("涉及国家/地区", "；".join(article.countries) or "未提供"),
        ("阶段判断依据", article.development_stage_evidence or "未提供"),
        ("阶段判断置信度", article.development_stage_confidence or "未提供"),
    ]
    lines = [f"{label}：{value}" for label, value in fields]
    lines.extend(["", "摘要：", article.abstract or "PubMed 未提供摘要。"])
    return "\n".join(lines)


def _pubmed_content_html(article: PubMedArticle) -> str:
    rows = [
        ("研究方向", article.topic),
        ("PMID", article.pmid),
        ("DOI", article.doi or "未提供"),
        ("期刊", article.journal or "未提供"),
        ("研发阶段", article.development_stage),
        ("证据等级", article.evidence_level),
        ("文献类型", "；".join(article.publication_types) or "未提供"),
        ("药物/化学物质", "；".join(article.drugs) or "未结构化标注"),
        ("作者", "；".join(article.authors) or "未提供"),
        ("机构", "；".join(article.organizations) or "未提供"),
        ("关键词", "；".join(article.keywords) or "未提供"),
        ("MeSH主题词", "；".join(article.mesh_terms) or "未提供"),
        ("靶点", "；".join(article.targets) or "未结构化标注"),
        ("申办方线索", "；".join(article.sponsor_hints) or "未提供"),
        ("临床试验编号", "；".join(article.trial_ids) or "未提供"),
        ("试验状态", article.trial_status or "未提供"),
        ("涉及国家/地区", "；".join(article.countries) or "未提供"),
        ("阶段判断依据", article.development_stage_evidence or "未提供"),
        ("阶段判断置信度", article.development_stage_confidence or "未提供"),
    ]
    table_rows = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>"
        for label, value in rows
    )
    abstract = html.escape(article.abstract or "PubMed 未提供摘要。").replace("\n", "<br>")
    return (
        "<article>"
        f"<h1>{html.escape(article.title)}</h1>"
        f"<table>{table_rows}</table>"
        f"<h2>摘要</h2><p>{abstract}</p>"
        "</article>"
    )


async def _collect_clinical_trials_topics(
    *,
    task_id: int,
    run_id: str,
    rules: dict[str, object],
    log_repo: LogRepository,
    data_repo: DataRepository,
) -> dict[str, int]:
    raw_topics = rules.get("topics")
    if not isinstance(raw_topics, list):
        raise ValueError("ClinicalTrials.gov rules require a topics list")

    topics: list[tuple[str, str | None, str | None, str | None]] = []
    for raw_topic in raw_topics:
        if not isinstance(raw_topic, dict):
            continue
        name = str(raw_topic.get("name") or "").strip()
        query = str(raw_topic.get("query") or "").strip()
        condition_query = str(raw_topic.get("condition_query") or "").strip()
        intervention_type = str(raw_topic.get("intervention_type") or "").strip()
        if name and (query or condition_query):
            topics.append(
                (
                    name,
                    query or None,
                    condition_query or None,
                    intervention_type or None,
                )
            )
    if not topics:
        raise ValueError("ClinicalTrials.gov rules contain no valid topic queries")

    max_results = _bounded_int(
        rules.get("max_results_per_topic"),
        default=25,
        minimum=1,
        maximum=100,
    )
    metrics = {
        "topics": len(topics),
        "discovered": 0,
        "stored": 0,
        "skipped_hash": 0,
        "failed": 0,
    }
    client = ClinicalTrialsGovClient()
    successful_topics = 0
    last_error: Exception | None = None
    for topic_name, query, condition_query, intervention_type in topics:
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
                if is_study_relevant_to_topic(study, topic_name)
            ]
            if not relevant_studies:
                raise ValueError(
                    f"ClinicalTrials.gov returned no relevant studies for {topic_name}"
                )
            successful_topics += 1
            metrics["discovered"] += len(relevant_studies)
        except Exception as exc:
            metrics["failed"] += 1
            last_error = exc
            await log_repo.create(
                level="ERROR",
                task_id=task_id,
                message=(
                    f"[run={run_id}] ClinicalTrials.gov topic failed: "
                    f"{topic_name}: {exc}"
                ),
                error_stack=str(exc),
            )
            continue

        for study in relevant_studies:
            try:
                outcome = await _store_clinical_trial(
                    task_id=task_id,
                    run_id=run_id,
                    topic=topic_name,
                    study=study,
                    log_repo=log_repo,
                    data_repo=data_repo,
                )
                metrics[outcome] += 1
            except Exception as exc:
                metrics["failed"] += 1
                last_error = exc
                await log_repo.create(
                    level="ERROR",
                    task_id=task_id,
                    message=(
                        f"[run={run_id}] ClinicalTrials.gov study failed: "
                        f"{topic_name} {study.nct_id or '(missing NCT id)'}"
                    ),
                    error_stack=str(exc),
                )

    if successful_topics == 0 and last_error is not None:
        raise last_error
    return metrics


async def _store_clinical_trial(
    *,
    task_id: int,
    run_id: str,
    topic: str,
    study: ClinicalTrialStudy,
    log_repo: LogRepository,
    data_repo: DataRepository,
) -> str:
    if not study.nct_id or not study.study_url:
        raise ValueError("ClinicalTrials.gov study is missing its NCT identifier")

    existing = await data_repo.get_by_source_url(study.study_url)
    topics = _merge_competitor_topics(
        getattr(existing, "metadata_json", None),
        topic,
        source="ClinicalTrials.gov",
    )
    metadata = {
        "kind": "competitor_intelligence",
        "source": "ClinicalTrials.gov",
        "topic": "、".join(topics),
        "topics": topics,
        "external_id": study.nct_id,
        "drugs": study.drug_assets,
        "targets": study.targets,
        "development_stage": study.phase or "临床试验（阶段未明确）",
        "evidence_level": "临床试验注册证据",
        "trial_ids": study.trial_ids,
        "trial_status": study.status,
        "sponsor": study.sponsor,
        "sponsor_hints": [study.sponsor] if study.sponsor else [],
        "collaborators": study.collaborators,
        "brief_summary": study.brief_summary,
        "conditions": study.conditions,
        "interventions": study.interventions,
        "countries": study.countries,
        "keywords": study.keywords,
    }
    title = study.brief_title or study.official_title or study.nct_id
    content_text = _clinical_trial_content_text(study, topics=topics)
    content_html = _clinical_trial_content_html(study, topics=topics)
    metadata_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
    content_hash = sha256_text(
        json.dumps(
            {
                "title": title,
                "summary": study.brief_summary,
                "metadata": metadata,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    quality = min(
        95,
        70
        + (5 if study.brief_summary else 0)
        + (5 if study.drug_assets else 0)
        + (5 if study.phase else 0)
        + (5 if study.sponsor else 0)
        + (5 if study.countries else 0),
    )
    summary = study.brief_summary[:500].strip() or (
        f"{'、'.join(topics)}；{metadata['development_stage']}；"
        f"{study.status or '状态未提供'}"
    )

    if existing is not None:
        if existing.content_hash == content_hash:
            metadata_update: dict[str, object] = {}
            if getattr(existing, "metadata_json", None) != metadata_json:
                metadata_update["metadata_json"] = metadata_json
            if existing.category != "竞品信息":
                metadata_update["category"] = "竞品信息"
            if metadata_update:
                await data_repo.update_review_metadata(existing, **metadata_update)
            return "skipped_hash"
        stored = await data_repo.update(
            existing,
            task_id=task_id,
            title=title,
            content_html=content_html,
            content_text=content_text,
            quality_score=quality,
            content_hash=content_hash,
            category="竞品信息",
            ai_summary=summary,
            metadata_json=metadata_json,
        )
    else:
        duplicate = await data_repo.get_by_hash(content_hash)
        if duplicate is not None:
            return "skipped_hash"
        stored = await data_repo.create(
            task_id=task_id,
            title=title,
            content_html=content_html,
            content_text=content_text,
            source_url=study.study_url,
            snapshot_path=None,
            quality_score=quality,
            content_hash=content_hash,
            category="竞品信息",
            ai_summary=summary,
            metadata_json=metadata_json,
        )

    try:
        snapshot_path = save_snapshot(data_id=stored.id, html=content_html)
        await data_repo.update_snapshot_path(data=stored, snapshot_path=snapshot_path)
    except Exception as exc:
        await log_repo.create(
            level="ERROR",
            task_id=task_id,
            message=(
                f"[run={run_id}] ClinicalTrials.gov snapshot save failed "
                f"for data {stored.id}"
            ),
            error_stack=str(exc),
        )

    await log_repo.create(
        level="INFO",
        task_id=task_id,
        message=(
            f"[run={run_id}] ClinicalTrials.gov stored {'、'.join(topics)} "
            f"{study.nct_id} as data item {stored.id}"
        ),
    )
    return "stored"


def _merge_competitor_topics(
    raw_metadata: str | None,
    current_topic: str,
    *,
    source: str,
) -> list[str]:
    topics: list[str] = []
    if raw_metadata:
        try:
            metadata = json.loads(raw_metadata)
        except (TypeError, ValueError):
            metadata = None
        if (
            isinstance(metadata, dict)
            and metadata.get("kind") == "competitor_intelligence"
            and metadata.get("source") == source
        ):
            raw_topics = metadata.get("topics")
            if isinstance(raw_topics, list):
                topics.extend(
                    str(item).strip()
                    for item in raw_topics
                    if str(item).strip()
                )
            elif isinstance(metadata.get("topic"), str):
                topics.extend(
                    item.strip()
                    for item in str(metadata["topic"]).split("、")
                    if item.strip()
                )
    normalized_topic = current_topic.strip()
    if normalized_topic and normalized_topic not in topics:
        topics.append(normalized_topic)
    return topics


def _clinical_trial_rows(
    study: ClinicalTrialStudy,
    *,
    topics: list[str],
) -> list[tuple[str, str]]:
    return [
        ("研究方向", "、".join(topics)),
        ("试验编号", study.nct_id),
        ("研发阶段", study.phase or "临床试验（阶段未明确）"),
        ("试验状态", study.status or "未提供"),
        ("申办方", study.sponsor or "未提供"),
        ("合作机构", "；".join(study.collaborators) or "未提供"),
        ("适应症", "；".join(study.conditions) or "未提供"),
        ("干预措施", "；".join(study.interventions) or "未提供"),
        ("药物/资产", "；".join(study.drug_assets) or "未结构化标注"),
        ("靶点", "；".join(study.targets) or "未结构化标注"),
        ("其他试验编号", "；".join(study.trial_ids) or "未提供"),
        ("国家/地区", "；".join(study.countries) or "未提供"),
        ("关键词", "；".join(study.keywords) or "未提供"),
    ]


def _clinical_trial_content_text(
    study: ClinicalTrialStudy,
    *,
    topics: list[str],
) -> str:
    lines = [
        f"{label}：{value}"
        for label, value in _clinical_trial_rows(study, topics=topics)
    ]
    lines.extend(["", "研究摘要：", study.brief_summary or "官方注册记录未提供摘要。"])
    return "\n".join(lines)


def _clinical_trial_content_html(
    study: ClinicalTrialStudy,
    *,
    topics: list[str],
) -> str:
    rows = "".join(
        f"<tr><th>{html.escape(label)}</th><td>{html.escape(value)}</td></tr>"
        for label, value in _clinical_trial_rows(study, topics=topics)
    )
    summary = html.escape(
        study.brief_summary or "官方注册记录未提供摘要。"
    ).replace("\n", "<br>")
    title = study.brief_title or study.official_title or study.nct_id
    return (
        "<article>"
        f"<h1>{html.escape(title)}</h1>"
        f"<table>{rows}</table>"
        f"<h2>研究摘要</h2><p>{summary}</p>"
        "</article>"
    )


def _bounded_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(parsed, maximum))


async def run_task(task_id: int) -> str:
    async with AsyncSessionLocal() as session:
        task_repo = TaskRepository(session)
        data_repo = DataRepository(session)
        log_repo = LogRepository(session)

        task = await task_repo.get_by_id(task_id)
        if task is None:
            await log_repo.create(
                level="ERROR",
                task_id=task_id,
                message=f"Task {task_id} not found",
            )
            raise ValueError(f"Task {task_id} not found")

        run_id = uuid.uuid4().hex[:12]
        await log_repo.create(
            level="INFO",
            task_id=task_id,
            message=f"[run={run_id}] Task {task_id} pipeline started",
        )

        run_outcome = "success"
        try:
            rules_loaded = _load_rules(task.parser_rules)
            crawl_mode = None
            if isinstance(rules_loaded, dict):
                raw_mode = rules_loaded.get("crawl_mode")
                if isinstance(raw_mode, str):
                    crawl_mode = raw_mode.strip().lower()

            if crawl_mode == "pubmed":
                pubmed_metrics = await _collect_pubmed_topics(
                    task_id=task_id,
                    run_id=run_id,
                    rules=rules_loaded,
                    log_repo=log_repo,
                    data_repo=data_repo,
                )
                await log_repo.create(
                    level="INFO",
                    task_id=task_id,
                    message=(
                        f"[run={run_id}] PubMed运行摘要："
                        f"主题 {pubmed_metrics['topics']}，"
                        f"发现 {pubmed_metrics['discovered']}，"
                        f"入库 {pubmed_metrics['stored']}，"
                        f"重复跳过 {pubmed_metrics['skipped_hash']}，"
                        f"失败 {pubmed_metrics['failed']}。"
                    ),
                    run_summary=_summary_payload_json(
                        run_id=run_id,
                        mode="pubmed",
                        metrics=pubmed_metrics,
                    ),
                )
                if int(pubmed_metrics.get("failed") or 0) > 0:
                    run_outcome = "partial"
            elif crawl_mode == "clinical_trials":
                clinical_metrics = await _collect_clinical_trials_topics(
                    task_id=task_id,
                    run_id=run_id,
                    rules=rules_loaded,
                    log_repo=log_repo,
                    data_repo=data_repo,
                )
                await log_repo.create(
                    level="INFO",
                    task_id=task_id,
                    message=(
                        f"[run={run_id}] ClinicalTrials.gov运行摘要："
                        f"主题 {clinical_metrics['topics']}，"
                        f"发现 {clinical_metrics['discovered']}，"
                        f"入库 {clinical_metrics['stored']}，"
                        f"重复跳过 {clinical_metrics['skipped_hash']}，"
                        f"失败 {clinical_metrics['failed']}。"
                    ),
                    run_summary=_summary_payload_json(
                        run_id=run_id,
                        mode="clinical_trials",
                        metrics=clinical_metrics,
                    ),
                )
                if int(clinical_metrics.get("failed") or 0) > 0:
                    run_outcome = "partial"
            elif crawl_mode == "meeting_table":
                meeting_metrics = await _collect_meeting_table(
                    task_id=task_id,
                    run_id=run_id,
                    start_url=task.start_url,
                    rules=rules_loaded,
                    log_repo=log_repo,
                    data_repo=data_repo,
                )
                await log_repo.create(
                    level="INFO",
                    task_id=task_id,
                    message=(
                        f"[run={run_id}] 会议日程运行摘要："
                        f"发现 {meeting_metrics['discovered']}，"
                        f"入库 {meeting_metrics['stored']}，"
                        f"重复跳过 {meeting_metrics['skipped_hash']}，"
                        f"失败 {meeting_metrics['failed']}。"
                    ),
                    run_summary=_summary_payload_json(
                        run_id=run_id,
                        mode="meeting_table",
                        metrics=meeting_metrics,
                    ),
                )
                if int(meeting_metrics.get("failed") or 0) > 0:
                    run_outcome = "partial"
            elif crawl_mode == "list_follow":
                list_budget = list_page_fetch_budget(rules_loaded)
                queue: deque[str] = deque(resolve_list_page_urls(task.start_url, rules_loaded))
                scheduled_list: set[str] = set(queue)
                delay_sec = list_request_delay_seconds(rules_loaded)
                detail_rules = detail_rules_json(rules_loaded)
                detail_sleep = detail_request_delay_seconds(rules_loaded)
                await log_repo.create(
                    level="INFO",
                    task_id=task_id,
                    message=(
                        f"[run={run_id}] list_follow: list fetch budget={list_budget}, initial queue={len(queue)}"
                    ),
                )
                detail_limit = detail_url_limit(rules_loaded)
                seen_detail: set[str] = set()
                detail_processed_count = 0
                detail_success_count = 0
                detail_skipped_count = 0
                detail_failed_count = 0
                last_error: Exception | None = None
                any_item_completed = False
                list_fetches = 0
                while queue and list_fetches < list_budget:
                    remaining = detail_limit - detail_processed_count
                    if remaining <= 0:
                        break
                    list_url = queue.popleft()
                    list_fetches += 1
                    list_html = await _download_page(
                        url=list_url,
                        log_repo=log_repo,
                        task_id=task_id,
                        run_id=run_id,
                        crawl_rules=rules_loaded,
                    )
                    batch = extract_list_follow_items(
                        list_html,
                        list_url,
                        rules_loaded,
                        url_cap=remaining,
                    )
                    unique_batch: list[dict[str, str]] = []
                    for item in batch:
                        u = item["url"]
                        if u in seen_detail:
                            continue
                        seen_detail.add(u)
                        unique_batch.append(item)

                    for batch_index, detail_item in enumerate(unique_batch):
                        if detail_processed_count >= detail_limit:
                            break
                        page_url = detail_item["url"]
                        detail_processed_count += 1
                        try:
                            outcome = await _collect_and_store_one_retrying(
                                task_id=task_id,
                                run_id=run_id,
                                page_url=page_url,
                                parser_rules=detail_rules,
                                log_repo=log_repo,
                                data_repo=data_repo,
                                crawl_rules=rules_loaded,
                                fallback_title=detail_item.get("title"),
                            )
                            if outcome == "stored":
                                detail_success_count += 1
                            elif outcome == "skipped_hash":
                                detail_skipped_count += 1
                            any_item_completed = True
                        except Exception as exc:
                            detail_failed_count += 1
                            last_error = exc
                            await log_repo.create(
                                level="ERROR",
                                task_id=task_id,
                                message=(
                                    f"[run={run_id}] list_follow failed on item "
                                    f"{detail_processed_count}/{detail_limit} {page_url}"
                                ),
                                error_stack=str(exc),
                            )

                        if (
                            detail_sleep > 0
                            and detail_processed_count < detail_limit
                            and (batch_index < len(unique_batch) - 1 or bool(queue))
                        ):
                            await asyncio.sleep(detail_sleep)

                    raw_next = rules_loaded.get("list_next_page")
                    if isinstance(raw_next, str) and raw_next.strip():
                        nxt = extract_next_list_page_url(list_html, list_url, rules_loaded)
                        if nxt is not None and nxt not in scheduled_list:
                            scheduled_list.add(nxt)
                            queue.append(nxt)

                    if (
                        delay_sec > 0
                        and queue
                        and list_fetches < list_budget
                        and (detail_limit - detail_processed_count) > 0
                    ):
                        await asyncio.sleep(delay_sec)
                if not seen_detail:
                    await log_repo.create(
                        level="WARNING",
                        task_id=task_id,
                        message=(
                            f"[run={run_id}] list_follow: no detail URLs from list page(s) "
                            f"(check list_item / detail_link selectors)"
                        ),
                    )
                    raise ValueError("list_follow produced zero detail URLs")

                detail_limit_hit = detail_processed_count >= detail_limit
                summary_metrics = {
                    "list_pages": list_fetches,
                    "detail_discovered": len(seen_detail),
                    "detail_processed": detail_processed_count,
                    "stored": detail_success_count,
                    "skipped_hash": detail_skipped_count,
                    "failed": detail_failed_count,
                    "detail_limit": detail_limit,
                    "detail_limit_hit": detail_limit_hit,
                    "remaining_list_queue": len(queue),
                }
                await log_repo.create(
                    level="INFO",
                    task_id=task_id,
                    message=(
                        f"[run={run_id}] 列表跟进运行摘要："
                        f"扫描列表页 {list_fetches}，发现详情 {len(seen_detail)}，"
                        f"处理 {detail_processed_count}，入库 {detail_success_count}，"
                        f"重复跳过 {detail_skipped_count}，失败 {detail_failed_count}。"
                    ),
                    run_summary=_summary_payload_json(
                        run_id=run_id,
                        mode="list_follow",
                        metrics=summary_metrics,
                    ),
                )
                if detail_failed_count > 0:
                    run_outcome = "partial"

                if not any_item_completed and last_error is not None:
                    raise last_error
            else:
                single_outcome = await _collect_and_store_one_retrying(
                    task_id=task_id,
                    run_id=run_id,
                    page_url=task.start_url,
                    parser_rules=task.parser_rules,
                    log_repo=log_repo,
                    data_repo=data_repo,
                    crawl_rules=rules_loaded if isinstance(rules_loaded, dict) else None,
                )
                single_stored = 1 if single_outcome == "stored" else 0
                single_skipped = 1 if single_outcome == "skipped_hash" else 0
                single_metrics = {
                    "processed": 1,
                    "stored": single_stored,
                    "skipped_hash": single_skipped,
                    "failed": 0,
                }
                await log_repo.create(
                    level="INFO",
                    task_id=task_id,
                    message=(
                        f"[run={run_id}] 单页运行摘要：处理 1，入库 {single_stored}，"
                        f"重复跳过 {single_skipped}，失败 0。"
                    ),
                    run_summary=_summary_payload_json(
                        run_id=run_id,
                        mode="single_page",
                        metrics=single_metrics,
                    ),
                )
        except Exception:
            await log_repo.create(
                level="ERROR",
                task_id=task_id,
                message=f"[run={run_id}] Task {task_id} pipeline execution failed",
                error_stack=traceback.format_exc(),
            )
            raise
        return run_outcome


async def _download_page(
    *,
    run_id: str,
    task_id: int,
    log_repo: LogRepository,
    url: str,
    crawl_rules: dict[str, object] | None = None,
) -> str:
    default_timeout = float(get_settings().timeout)
    timeout_sec = fetch_timeout_seconds(crawl_rules, default_timeout)
    extra_headers = fetch_http_headers(crawl_rules)
    jar = fetch_http_cookies(crawl_rules)
    cookie_domain = fetch_cookie_domain_override(crawl_rules)
    login_flow = fetch_login_flow(crawl_rules)
    proxy_config = fetch_proxy_config(crawl_rules)
    dynamic_wait_selector_raw = (
        crawl_rules.get("dynamic_wait_selector") if crawl_rules else None
    )
    dynamic_wait_selector = (
        dynamic_wait_selector_raw.strip()
        if isinstance(dynamic_wait_selector_raw, str)
        and dynamic_wait_selector_raw.strip()
        else None
    )
    if isinstance(login_flow, dict):
        session_key = login_flow.get("session_key")
        if not isinstance(session_key, str) or not session_key.strip():
            login_flow["session_key"] = f"task:{task_id}"
    block_status_codes = anti_bot_block_status_codes(crawl_rules)
    block_backoff_sec = anti_bot_block_backoff_seconds(crawl_rules)
    retry_on_block = anti_bot_retry_on_block(crawl_rules)

    static_exc: Exception | None = None
    force_dynamic = bool(crawl_rules and crawl_rules.get("force_dynamic_fetch"))
    if not force_dynamic:
        try:
            static_html = await fetch_static(
                url,
                timeout=timeout_sec,
                headers=extra_headers,
                cookies=jar,
            )
            if not looks_like_anti_bot_challenge(static_html, crawl_rules):
                return static_html
            await log_repo.create(
                level="WARNING",
                task_id=task_id,
                message=(
                    f"[run={run_id}] Static fetch returned suspected anti-bot challenge for "
                    f"{url}, falling back to dynamic fetch"
                ),
            )
        except Exception as exc:
            static_exc = exc
            message = f"[run={run_id}] Static fetch failed for {url}, falling back to dynamic fetch"
            if isinstance(exc, httpx.HTTPStatusError):
                status_code = exc.response.status_code if exc.response is not None else 0
                if status_code in block_status_codes:
                    message = (
                        f"[run={run_id}] Static fetch hit anti-bot status {status_code} for {url}, "
                        "falling back to dynamic fetch"
                    )
                    if block_backoff_sec > 0:
                        await asyncio.sleep(block_backoff_sec)
            await log_repo.create(
                level="WARNING",
                task_id=task_id,
                message=message,
                error_stack=str(exc),
            )
    else:
        await log_repo.create(
            level="INFO",
            task_id=task_id,
            message=f"[run={run_id}] Dynamic fetch forced for {url}",
        )

    proxy_on_block_only = True
    proxy_failover_enabled = True
    if isinstance(proxy_config, dict):
        proxy_on_block_only = bool(proxy_config.get("on_block_only", True))
        proxy_failover_enabled = bool(proxy_config.get("failover_enabled", True))

    primary_proxy = proxy_config if (proxy_config and not proxy_on_block_only) else None

    try:
        dynamic_html = await fetch_dynamic(
            url,
            timeout=timeout_sec,
            headers=extra_headers,
            cookies=jar,
            cookie_domain=cookie_domain,
            login_flow=login_flow,
            proxy=primary_proxy,
            wait_for_selector=dynamic_wait_selector,
        )
    except Exception as dynamic_exc:
        if proxy_config and proxy_on_block_only and proxy_failover_enabled:
            await log_repo.create(
                level="WARNING",
                task_id=task_id,
                message=(f"[run={run_id}] Dynamic fetch failed for {url}, retrying with proxy"),
                error_stack=str(dynamic_exc),
            )
            dynamic_html = await fetch_dynamic(
                url,
                timeout=timeout_sec,
                headers=extra_headers,
                cookies=jar,
                cookie_domain=cookie_domain,
                login_flow=login_flow,
                proxy=proxy_config,
                wait_for_selector=dynamic_wait_selector,
            )
        else:
            raise

    if looks_like_anti_bot_challenge(dynamic_html, crawl_rules):
        await log_repo.create(
            level="WARNING",
            task_id=task_id,
            message=(f"[run={run_id}] Dynamic fetch still looks like anti-bot challenge for {url}"),
            error_stack=str(static_exc) if static_exc is not None else None,
        )
        if proxy_config and proxy_on_block_only and proxy_failover_enabled:
            await log_repo.create(
                level="WARNING",
                task_id=task_id,
                message=(f"[run={run_id}] Challenge detected for {url}, retrying dynamic fetch with proxy"),
            )
            proxied_html = await fetch_dynamic(
                url,
                timeout=timeout_sec,
                headers=extra_headers,
                cookies=jar,
                cookie_domain=cookie_domain,
                login_flow=login_flow,
                proxy=proxy_config,
                wait_for_selector=dynamic_wait_selector,
            )
            if not looks_like_anti_bot_challenge(proxied_html, crawl_rules):
                return proxied_html
            dynamic_html = proxied_html
        if retry_on_block:
            raise AntiBotBlockedError(f"anti-bot challenge detected for {url}")
    return dynamic_html


async def _parse_page(
    html: str,
    *,
    parser_rules: str | None,
    source_url: str,
    log_repo: LogRepository,
    task_id: int,
    run_id: str,
) -> dict[str, str | None]:
    parsed: dict[str, str | None] = {"title": None, "content_html": None, "source_url": source_url}

    try:
        rules = _load_rules(parser_rules)
    except Exception as exc:
        await log_repo.create(
            level="WARNING",
            task_id=task_id,
            message=f"[run={run_id}] Invalid parser_rules detected, falling back to readability parser",
            error_stack=str(exc),
        )
        rules = None

    if rules:
        try:
            parsed.update(parse_with_rules(html, rules))
        except Exception as exc:
            await log_repo.create(
                level="WARNING",
                task_id=task_id,
                message=f"[run={run_id}] Rule-based parsing failed, falling back to readability parser",
                error_stack=str(exc),
            )

    if not parsed.get("content_html"):
        parsed.update(parse_with_readability(html))

    if not parsed.get("content_html"):
        parsed["content_html"] = html

    return parsed


def _load_rules(raw_rules: str | None) -> dict[str, object] | None:
    if not raw_rules:
        return None

    loaded = json.loads(raw_rules)
    if not isinstance(loaded, dict):
        raise ValueError("parser_rules must decode to an object")
    return loaded


GENERIC_PLATFORM_TITLES = {
    "国家科技管理信息系统公共服务平台",
    "国家科技管理信息系统 公共服务平台",
}


def _best_title(
    parsed_title: str | None,
    fallback_title: str | None,
    *,
    prefer_fallback: bool = False,
) -> str | None:
    fallback = " ".join((fallback_title or "").split())
    parsed = " ".join((parsed_title or "").split())
    if prefer_fallback and fallback:
        return fallback
    if fallback and (not parsed or parsed in GENERIC_PLATFORM_TITLES):
        return fallback
    return parsed or fallback or None


def _unchanged_metadata_update(
    existing_title: str | None,
    parsed_title: str | None,
    existing_summary: str | None,
    parsed_summary: str | None,
    *,
    prefer_incoming_title: bool = False,
) -> dict[str, str]:
    update: dict[str, str] = {}
    better_title = _best_title(
        existing_title,
        parsed_title,
        prefer_fallback=prefer_incoming_title,
    )
    if better_title and better_title != (existing_title or ""):
        update["title"] = better_title
    if parsed_summary and parsed_summary != (existing_summary or ""):
        update["ai_summary"] = parsed_summary
    return update
