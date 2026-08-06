import csv
import io
import json
import re
from pathlib import Path

from app.repositories.data_repo import DataRepository
from app.repositories.log_repo import LogRepository
from app.repositories.task_repo import TaskRepository
from app.schemas.common import (
    LogRead,
    LogSummary,
    PageData,
    RunSummaryPayload,
    StatsOverview,
)
from app.schemas.data import DataListItem, DataRead, DataReviewUpdate, SnapshotRead
from app.utils.notice import build_notice_summary, normalize_review_status


_RUN_ID_RE = re.compile(r"\[run=(?P<run_id>[0-9a-zA-Z_-]+)\]")
_SUMMARY_RE = re.compile(r"(?P<mode>list_follow|single_page)\s+summary:\s*(?P<body>.+)$")


def _parse_metrics_text(body: str) -> dict[str, str | int | bool]:
    metrics: dict[str, str | int | bool] = {}
    for chunk in body.split(","):
        part = chunk.strip()
        if "=" not in part:
            continue
        key, raw_value = part.split("=", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key or not value:
            continue

        lowered = value.lower()
        if lowered in {"true", "false"}:
            metrics[key] = lowered == "true"
            continue
        try:
            metrics[key] = int(value)
            continue
        except ValueError:
            metrics[key] = value
    return metrics


def _competitor_export_fields(raw_metadata: str | None) -> dict[str, str]:
    if not raw_metadata:
        return {}
    try:
        metadata = json.loads(raw_metadata)
    except (TypeError, ValueError):
        return {}
    if not isinstance(metadata, dict):
        return {}

    def text_value(key: str) -> str:
        value = metadata.get(key)
        if isinstance(value, list):
            return "；".join(
                str(item).strip()
                for item in value
                if str(item).strip()
            )
        return str(value).strip() if value is not None else ""

    return {
        "topic": text_value("topic"),
        "external_id": text_value("external_id"),
        "doi": text_value("doi"),
        "journal": text_value("journal"),
        "drugs": text_value("drugs"),
        "development_stage": text_value("development_stage"),
        "evidence_level": text_value("evidence_level"),
        "authors": text_value("authors"),
        "organizations": text_value("organizations"),
    }


def parse_run_summary_from_log(
    *,
    message: str,
    run_summary: str | None,
    error_stack: str | None,
) -> RunSummaryPayload | None:
    text = (message or "").strip()
    if run_summary:
        try:
            raw = json.loads(run_summary)
            if (
                isinstance(raw, dict)
                and raw.get("kind") == "run_summary"
                and isinstance(raw.get("mode"), str)
                and isinstance(raw.get("metrics"), dict)
            ):
                metrics_dict = {str(k): v for k, v in raw["metrics"].items() if isinstance(v, (str, int, bool))}
                return RunSummaryPayload(
                    run_id=raw.get("run_id") if isinstance(raw.get("run_id"), str) else None,
                    mode=raw["mode"],
                    metrics=metrics_dict,
                )
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # Backward compatibility for older rows where structured summary lived in error_stack.
    if error_stack:
        try:
            raw = json.loads(error_stack)
            if (
                isinstance(raw, dict)
                and raw.get("kind") == "run_summary"
                and isinstance(raw.get("mode"), str)
                and isinstance(raw.get("metrics"), dict)
            ):
                metrics_dict = {str(k): v for k, v in raw["metrics"].items() if isinstance(v, (str, int, bool))}
                return RunSummaryPayload(
                    run_id=raw.get("run_id") if isinstance(raw.get("run_id"), str) else None,
                    mode=raw["mode"],
                    metrics=metrics_dict,
                )
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    if not text:
        return None
    summary_match = _SUMMARY_RE.search(text)
    if summary_match is None:
        return None

    metrics = _parse_metrics_text(summary_match.group("body"))
    run_match = _RUN_ID_RE.search(text)
    run_id = run_match.group("run_id") if run_match else None

    return RunSummaryPayload(
        run_id=run_id,
        mode=summary_match.group("mode"),
        metrics=metrics,
    )


class DataService:
    def __init__(
        self,
        data_repo: DataRepository,
        task_repo: TaskRepository,
        log_repo: LogRepository,
    ):
        self.data_repo = data_repo
        self.task_repo = task_repo
        self.log_repo = log_repo
        self.server_dir = Path(__file__).resolve().parents[2]

    async def list_data(
        self,
        *,
        page: int,
        page_size: int,
        task_id: int | None = None,
        category: str | None = None,
        review_status: str | None = None,
        archived: bool | None = None,
    ) -> PageData[DataListItem]:
        items, total = await self.data_repo.list_paginated(
            page=page,
            page_size=page_size,
            task_id=task_id,
            category=category,
            review_status=review_status,
            archived=archived,
        )
        return PageData[DataListItem](
            items=[DataListItem.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_data(self, data_id: int) -> DataRead:
        data = await self.data_repo.get_by_id(data_id)
        if data is None:
            raise LookupError(f"Collected data {data_id} not found")
        return DataRead.model_validate(data)

    async def update_review(self, data_id: int, payload: DataReviewUpdate) -> DataRead:
        data = await self.data_repo.get_by_id(data_id)
        if data is None:
            raise LookupError(f"Collected data {data_id} not found")

        updates = payload.model_dump(exclude_unset=True)
        if "review_status" in updates and updates["review_status"] is not None:
            updates["review_status"] = normalize_review_status(updates["review_status"])
        if "remark" in updates and updates["remark"] is not None:
            updates["remark"] = updates["remark"].strip() or None
        if "category" in updates and updates["category"] is not None:
            updates["category"] = updates["category"].strip() or "未分类"

        updated = await self.data_repo.update_review_metadata(data, **updates)
        return DataRead.model_validate(updated)

    async def get_snapshot_content(self, data_id: int) -> SnapshotRead:
        data = await self.data_repo.get_by_id(data_id)
        if data is None:
            raise LookupError(f"Collected data {data_id} not found")
        if not data.snapshot_path:
            raise FileNotFoundError(f"Snapshot for data {data_id} not found")

        snapshot_path = self.server_dir / data.snapshot_path
        if not snapshot_path.exists():
            raise FileNotFoundError(f"Snapshot file {snapshot_path} not found")
        return SnapshotRead(
            id=data.id,
            snapshot_path=data.snapshot_path,
            content=snapshot_path.read_text(encoding="utf-8"),
        )

    async def list_logs(
        self,
        *,
        page: int,
        page_size: int,
        task_id: int | None = None,
        level: str | None = None,
        message_contains: str | None = None,
        only_summary: bool = False,
    ) -> PageData[LogRead]:
        needle = (message_contains or "").strip()
        if len(needle) > 500:
            needle = needle[:500]

        items, total = await self.log_repo.list_paginated(
            page=page,
            page_size=page_size,
            task_id=task_id,
            level=level,
            message_contains=needle or None,
            only_summary=only_summary,
        )
        logs = [
            LogRead(
                id=item.id,
                task_id=item.task_id,
                level=item.level,
                message=item.message,
                error_stack=item.error_stack,
                run_summary=parse_run_summary_from_log(
                    message=item.message,
                    run_summary=item.run_summary,
                    error_stack=item.error_stack,
                ),
                created_at=item.created_at,
            )
            for item in items
        ]
        return PageData[LogRead](
            items=logs,
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_overview_stats(self) -> StatsOverview:
        total_tasks = await self.task_repo.count_all()
        enabled_tasks = await self.task_repo.count_enabled()
        total_data = await self.data_repo.count_all()
        today_data = await self.data_repo.count_today()
        total_logs = await self.log_repo.count_all()
        avg_quality_score = await self.data_repo.average_quality_score()

        return StatsOverview(
            total_tasks=total_tasks,
            enabled_tasks=enabled_tasks,
            total_data=total_data,
            today_data=today_data,
            total_logs=total_logs,
            avg_quality_score=avg_quality_score,
        )

    async def get_log_summary(self) -> LogSummary:
        total_logs = await self.log_repo.count_all()
        info_logs = await self.log_repo.count_by_level("INFO")
        warning_logs = await self.log_repo.count_by_level("WARNING")
        error_logs = await self.log_repo.count_by_level("ERROR")
        failed_task_count = await self.log_repo.count_failed_tasks()

        return LogSummary(
            total_logs=total_logs,
            info_logs=info_logs,
            warning_logs=warning_logs,
            error_logs=error_logs,
            failed_task_count=failed_task_count,
        )

    async def export_collected_data_csv(
        self,
        *,
        task_id: int | None,
        limit: int,
        category: str | None = None,
        review_status: str | None = None,
        archived: bool | None = None,
    ) -> bytes:
        rows = await self.data_repo.list_recent_for_export(
            task_id=task_id,
            limit=limit,
            category=category,
            review_status=review_status,
            archived=archived,
        )
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "id",
                "task_id",
                "title",
                "category",
                "competitor_topic",
                "external_id",
                "doi",
                "journal",
                "drugs_or_chemicals",
                "development_stage",
                "evidence_level",
                "authors",
                "organizations",
                "review_status",
                "is_archived",
                "source_url",
                "quality_score",
                "published_at",
                "fetch_time",
                "ai_summary",
                "remark",
                "content_hash",
                "snapshot_path",
                "content_preview",
            ],
        )
        for row in rows:
            preview = (row.content_text or "")[:4000].replace("\r\n", "\n").replace("\r", "\n")
            ft = row.fetch_time.isoformat() if row.fetch_time else ""
            published_at = row.published_at.isoformat() if row.published_at else ""
            competitor = _competitor_export_fields(row.metadata_json)
            writer.writerow(
                [
                    row.id,
                    row.task_id,
                    row.title or "",
                    row.category,
                    competitor.get("topic", ""),
                    competitor.get("external_id", ""),
                    competitor.get("doi", ""),
                    competitor.get("journal", ""),
                    competitor.get("drugs", ""),
                    competitor.get("development_stage", ""),
                    competitor.get("evidence_level", ""),
                    competitor.get("authors", ""),
                    competitor.get("organizations", ""),
                    row.review_status,
                    "yes" if row.is_archived else "no",
                    row.source_url,
                    row.quality_score,
                    published_at,
                    ft,
                    row.ai_summary or build_notice_summary(row.content_text),
                    row.remark or "",
                    row.content_hash or "",
                    row.snapshot_path or "",
                    preview,
                ],
            )
        return ("\ufeff" + buffer.getvalue()).encode("utf-8")

    async def export_collected_data_excel_compatible(
        self,
        *,
        task_id: int | None,
        limit: int,
        category: str | None = None,
        review_status: str | None = None,
        archived: bool | None = None,
    ) -> bytes:
        rows = await self.data_repo.list_recent_for_export(
            task_id=task_id,
            limit=limit,
            category=category,
            review_status=review_status,
            archived=archived,
        )
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "标题",
                "类别",
                "研究方向",
                "PMID/外部编号",
                "DOI",
                "期刊",
                "药物/化学物质",
                "研发阶段",
                "证据等级",
                "作者",
                "研究机构",
                "来源",
                "发布时间",
                "采集时间",
                "摘要",
                "链接",
                "标记状态",
                "是否归档",
                "备注",
                "任务ID",
            ],
        )
        for row in rows:
            competitor = _competitor_export_fields(row.metadata_json)
            writer.writerow(
                [
                    row.title or "",
                    row.category,
                    competitor.get("topic", ""),
                    competitor.get("external_id", ""),
                    competitor.get("doi", ""),
                    competitor.get("journal", ""),
                    competitor.get("drugs", ""),
                    competitor.get("development_stage", ""),
                    competitor.get("evidence_level", ""),
                    competitor.get("authors", ""),
                    competitor.get("organizations", ""),
                    row.source_url,
                    row.published_at.isoformat() if row.published_at else "",
                    row.fetch_time.isoformat() if row.fetch_time else "",
                    row.ai_summary or build_notice_summary(row.content_text),
                    row.source_url,
                    row.review_status,
                    "是" if row.is_archived else "否",
                    row.remark or "",
                    row.task_id,
                ],
            )
        return ("\ufeff" + buffer.getvalue()).encode("utf-8")
