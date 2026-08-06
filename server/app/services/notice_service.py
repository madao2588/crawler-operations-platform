import json
from pathlib import Path

from app.repositories.data_repo import DataRepository
from app.repositories.keyword_rule_repo import KeywordRepository
from app.schemas.common import PageData
from app.schemas.notice import (
    NoticeListItem,
    NoticeMonthOption,
    NoticeRead,
    NoticeSnapshotRead,
    NoticeSourceSiteOption,
)
from app.utils.notice import (
    build_notice_summary,
    classify_notice_category,
    effective_active_keywords,
    effective_high_priority_keywords,
    extract_matched_keywords,
    extract_source_site,
    is_high_priority_notice,
    project_notice_kind,
)


class NoticeService:
    def __init__(self, data_repo: DataRepository, keyword_repo: KeywordRepository):
        self.data_repo = data_repo
        self.keyword_repo = keyword_repo
        self.server_dir = Path(__file__).resolve().parents[2]

    async def _get_keyword_lists(self) -> tuple[list[str], list[str]]:
        rules = await self.keyword_repo.get_active()
        active_raw = [r.word for r in rules if r.is_active]
        high_priority_raw = [r.word for r in rules if r.is_high_priority and r.is_active]
        active = effective_active_keywords(active_raw)
        high_priority = effective_high_priority_keywords(high_priority_raw)
        return active, high_priority

    async def list_notices(
        self,
        *,
        page: int,
        page_size: int,
        keyword: str | None = None,
        category: str | None = None,
        review_status: str | None = None,
        archived: bool | None = None,
        captured_today: bool | None = None,
        month: str | None = None,
        source_site: str | None = None,
        keyword_hit: bool | None = None,
        high_priority: bool | None = None,
        high_quality: bool | None = None,
        project_signal: str | None = None,
    ) -> PageData[NoticeListItem]:
        active_kws, high_pri_kws = await self._get_keyword_lists()
        items, total = await self.data_repo.list_paginated(
            page=page,
            page_size=page_size,
            keyword=keyword,
            category=category,
            review_status=review_status,
            archived=archived,
            captured_today=captured_today,
            month=month,
            source_site=source_site,
            keyword_hit=keyword_hit,
            high_priority=high_priority,
            high_quality=high_quality,
            project_signal=project_signal,
            enabled_only=True,
            include_disabled_history=True,
            active_keywords_for_sort=active_kws or None,
            active_keywords_for_filter=active_kws,
            high_priority_keywords=high_pri_kws,
        )
        notices = [self._to_notice_list_item(item, active_kws, high_pri_kws) for item in items]
        return PageData[NoticeListItem](
            items=notices,
            total=total,
            page=page,
            page_size=page_size,
        )

    async def list_months(
        self,
        *,
        keyword: str | None = None,
        category: str | None = None,
        review_status: str | None = None,
        archived: bool | None = None,
        captured_today: bool | None = None,
        source_site: str | None = None,
        keyword_hit: bool | None = None,
        high_priority: bool | None = None,
        high_quality: bool | None = None,
        project_signal: str | None = None,
    ) -> list[NoticeMonthOption]:
        active_kws, high_pri_kws = await self._get_keyword_lists()
        rows = await self.data_repo.aggregate_notice_months(
            keyword=keyword,
            category=category,
            review_status=review_status,
            archived=archived,
            captured_today=captured_today,
            source_site=source_site,
            keyword_hit=keyword_hit,
            high_priority=high_priority,
            high_quality=high_quality,
            project_signal=project_signal,
            enabled_only=True,
            include_disabled_history=True,
            active_keywords_for_filter=active_kws,
            high_priority_keywords=high_pri_kws,
        )
        return [NoticeMonthOption(month=month, count=count) for month, count in rows]

    async def list_source_sites(self) -> list[NoticeSourceSiteOption]:
        rows = await self.data_repo.aggregate_source_site_task_counts(
            enabled_only=True,
            include_disabled_history=True,
        )
        grouped: dict[str, dict[str, int | str]] = {}
        for source_site, task_name, notice_count in rows:
            if not source_site:
                continue
            current = grouped.setdefault(
                source_site,
                {
                    "total": 0,
                    "best_count": -1,
                    "task_name": task_name,
                },
            )
            current["total"] = int(current["total"]) + notice_count
            best_count = int(current["best_count"])
            best_name = str(current["task_name"])
            if notice_count > best_count or (notice_count == best_count and task_name < best_name):
                current["best_count"] = notice_count
                current["task_name"] = task_name

        ranked = sorted(
            grouped.items(),
            key=lambda item: (-int(item[1]["total"]), item[0]),
        )
        return [
            NoticeSourceSiteOption(
                source_site=source_site,
                display_name=_source_display_name(str(values["task_name"])),
            )
            for source_site, values in ranked
        ]

    async def get_notice(self, notice_id: int) -> NoticeRead:
        data = await self.data_repo.get_by_id(notice_id)
        if data is None:
            raise LookupError(f"Notice {notice_id} not found")

        active_kws, high_pri_kws = await self._get_keyword_lists()
        matched_keywords = extract_matched_keywords([data.title, data.content_text], active_kws)
        metadata = _load_metadata(data.metadata_json)
        return NoticeRead(
            id=data.id,
            title=data.title or "",
            summary=data.ai_summary or build_notice_summary(data.content_text),
            source_site=extract_source_site(data.source_url),
            source_url=data.source_url,
            published_at=data.published_at,
            captured_at=data.fetch_time,
            quality_score=data.quality_score,
            matched_keywords=matched_keywords,
            is_high_priority=is_high_priority_notice(
                matched_keywords=matched_keywords,
                high_priority_keywords=high_pri_kws,
            ),
            project_signal=project_notice_kind(
                [data.title, data.content_text, data.ai_summary],
                category=data.category,
                metadata=metadata,
            ),
            category=data.category or classify_notice_category([data.title, data.content_text]),
            ai_summary=data.ai_summary,
            review_status=data.review_status,
            is_archived=data.is_archived,
            remark=data.remark,
            task_id=data.task_id,
            content_text=data.content_text or "",
            content_html=data.content_html or "",
            content_hash=data.content_hash,
            snapshot_path=data.snapshot_path,
            metadata=metadata,
        )

    async def get_notice_snapshot(self, notice_id: int) -> NoticeSnapshotRead:
        data = await self.data_repo.get_by_id(notice_id)
        if data is None:
            raise LookupError(f"Notice {notice_id} not found")
        if not data.snapshot_path:
            raise FileNotFoundError(f"Snapshot for notice {notice_id} not found")

        snapshot_path = self.server_dir / data.snapshot_path
        if not snapshot_path.exists():
            raise FileNotFoundError(f"Snapshot file {snapshot_path} not found")

        return NoticeSnapshotRead(
            id=data.id,
            source_url=data.source_url,
            source_site=extract_source_site(data.source_url),
            snapshot_path=data.snapshot_path,
            content=snapshot_path.read_text(encoding="utf-8"),
        )

    def _to_notice_list_item(
        self, item, active_keywords: list[str], high_priority_keywords: list[str]
    ) -> NoticeListItem:
        matched_keywords = extract_matched_keywords([item.title, item.content_text], active_keywords)
        metadata = _load_metadata(item.metadata_json)
        return NoticeListItem(
            id=item.id,
            title=item.title or "",
            summary=item.ai_summary or build_notice_summary(item.content_text),
            source_site=extract_source_site(item.source_url),
            source_url=item.source_url,
            published_at=item.published_at,
            captured_at=item.fetch_time,
            quality_score=item.quality_score,
            matched_keywords=matched_keywords,
            is_high_priority=is_high_priority_notice(
                matched_keywords=matched_keywords,
                high_priority_keywords=high_priority_keywords,
            ),
            project_signal=project_notice_kind(
                [item.title, item.content_text, item.ai_summary],
                category=item.category,
                metadata=metadata,
            ),
            category=item.category or classify_notice_category([item.title, item.content_text]),
            ai_summary=item.ai_summary,
            review_status=item.review_status,
            is_archived=item.is_archived,
            remark=item.remark,
            task_id=item.task_id,
        )


def _load_metadata(raw_value: str | None) -> dict[str, object] | None:
    if not raw_value:
        return None
    try:
        value = json.loads(raw_value)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _source_display_name(task_name: str) -> str:
    display_name = task_name.strip()
    for suffix in ("线索登记", "采集", "入口"):
        if display_name.endswith(suffix):
            display_name = display_name[: -len(suffix)].rstrip()
            break
    return display_name or "未命名来源"
