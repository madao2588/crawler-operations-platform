from collections import Counter
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.runtime_status import get_runtime_snapshot
from app.repositories.data_repo import DataRepository
from app.repositories.keyword_rule_repo import KeywordRepository
from app.repositories.task_repo import TaskRepository
from app.schemas.dashboard import (
    DashboardCollectionIssue,
    DashboardMetrics,
    DashboardOverview,
    DashboardCollectionHealth,
    DashboardRuntime,
    KeywordHeatItem,
    ProjectSignalItem,
    SourceDistributionItem,
)
from app.services.notice_service import NoticeService
from app.utils.task_retry import classify_failure, is_retry_backoff_active


class DashboardService:
    def __init__(self, data_repo: DataRepository, task_repo: TaskRepository, keyword_repo: KeywordRepository):
        self.data_repo = data_repo
        self.task_repo = task_repo
        self.keyword_repo = keyword_repo
        self.notice_service = NoticeService(data_repo=data_repo, keyword_repo=keyword_repo)

    async def get_overview(self) -> DashboardOverview:
        snap = await get_runtime_snapshot()
        runtime = DashboardRuntime(
            status=snap["status"],
            database=snap["database"],
            scheduler=snap["scheduler"],
            scheduled_jobs=snap["scheduled_jobs"],
            release_version=get_settings().release_version,
        )

        active_kws, high_pri_kws = await self.notice_service._get_keyword_lists()

        recent_items, _ = await self.data_repo.list_paginated(
            page=1,
            page_size=20,
            enabled_only=True,
            include_disabled_history=True,
        )
        high_priority_items, _ = await self.data_repo.list_paginated(
            page=1,
            page_size=5,
            enabled_only=True,
            include_disabled_history=True,
            active_keywords_for_filter=active_kws,
            high_priority_keywords=high_pri_kws,
            high_priority=True,
            quality_first=True,
        )
        enabled_tasks = await self.task_repo.list_enabled()
        collection_health = self._build_collection_health(enabled_tasks)

        recent_notices = [
            self.notice_service._to_notice_list_item(item, active_kws, high_pri_kws) for item in recent_items[:5]
        ]
        high_value_notices = [
            self.notice_service._to_notice_list_item(item, active_kws, high_pri_kws) for item in high_priority_items
        ]

        metrics = await self.data_repo.aggregate_dashboard_metrics(
            active_keywords=active_kws,
            high_priority_keywords=high_pri_kws,
        )
        source_rows = await self.data_repo.aggregate_source_site_task_counts(
            enabled_only=True,
            include_disabled_history=True,
        )
        source_options = self.notice_service.build_source_site_options(source_rows)
        source_display_names = {option.source_site: option.display_name for option in source_options}
        source_counter = Counter()
        for source_site, _task_name, count in source_rows:
            source_counter[source_site] += count
        source_total = sum(source_counter.values())
        source_counts = sorted(source_counter.items(), key=lambda item: (-item[1], item[0]))[:10]
        keyword_counts = await self.data_repo.aggregate_keyword_hits(
            active_keywords=active_kws,
            enabled_only=True,
            include_disabled_history=True,
        )
        project_signal_counts = [
            ("申报通知", metrics["project_declaration_notices"]),
            ("结果公示", metrics["result_publication_notices"]),
            ("其他项目线索", metrics["other_project_notices"]),
        ]
        source_distribution = [
            SourceDistributionItem(
                source_site=source_site,
                display_name=source_display_names.get(source_site, source_site or "未命名来源"),
                notice_count=count,
                percentage=round((count / source_total) * 100, 2) if source_total else 0,
            )
            for source_site, count in source_counts
        ]
        keyword_heat = [KeywordHeatItem(keyword=keyword, count=count) for keyword, count in keyword_counts]
        project_signal_total = sum(count for _, count in project_signal_counts)
        project_signal_distribution = [
            ProjectSignalItem(
                label=label,
                notice_count=count,
                percentage=round((count / project_signal_total) * 100, 2) if project_signal_total else 0,
            )
            for label, count in project_signal_counts
        ]
        last_updated_at = recent_notices[0].captured_at if recent_notices else None

        return DashboardOverview(
            metrics=DashboardMetrics(
                today_new_notices=metrics["today_new_notices"],
                keyword_hit_notices=metrics["keyword_hit_notices"],
                monitoring_site_count=len(enabled_tasks),
                high_priority_notices=metrics["high_priority_notices"],
                high_quality_notices=metrics["high_quality_notices"],
                project_declaration_notices=metrics["project_declaration_notices"],
                result_publication_notices=metrics["result_publication_notices"],
            ),
            runtime=runtime,
            collection_health=collection_health,
            high_value_notices=high_value_notices,
            recent_notices=recent_notices,
            keyword_heat=keyword_heat,
            source_distribution=source_distribution,
            project_signal_distribution=project_signal_distribution,
            last_updated_at=last_updated_at,
        )

    @staticmethod
    def _build_collection_health(enabled_tasks) -> DashboardCollectionHealth:
        now = datetime.now(timezone.utc)
        stale_before = now - timedelta(hours=24)
        failed_tasks = [task for task in enabled_tasks if task.last_run_status == "failed"]
        partial_tasks = [task for task in enabled_tasks if task.last_run_status == "partial"]
        stale_tasks = [
            task
            for task in enabled_tasks
            if _as_utc(task.last_success_at) is None
            or _as_utc(task.last_success_at) < stale_before
        ]
        freshness_tasks = failed_tasks or partial_tasks or list(enabled_tasks)
        successful_at = [
            value
            for task in freshness_tasks
            if (value := _as_utc(task.last_success_at)) is not None
        ]
        if not enabled_tasks:
            status = "idle"
        elif len(failed_tasks) == len(enabled_tasks):
            status = "error"
        elif failed_tasks or partial_tasks or stale_tasks:
            status = "warning"
        else:
            status = "healthy"
        issues = []
        backoff_count = 0
        for task in enabled_tasks:
            last_success_at = _as_utc(task.last_success_at)
            is_stale = last_success_at is None or last_success_at < stale_before
            run_status = (task.last_run_status or "").strip().lower()
            backoff_active, failure_kind, next_retry_at = is_retry_backoff_active(
                now=now,
                last_run_status=task.last_run_status,
                last_run_at=task.last_run_at,
                last_error_message=task.last_error_message,
            )
            if backoff_active:
                backoff_count += 1
            if run_status not in {"failed", "partial"} and not is_stale:
                continue
            issue_status = run_status if run_status in {"failed", "partial"} else "stale"
            issues.append(
                DashboardCollectionIssue(
                    task_id=task.id,
                    task_name=task.name,
                    status=issue_status,
                    reason=_collection_issue_reason(
                        status=issue_status,
                        raw_error=task.last_error_message,
                        is_stale=is_stale,
                    ),
                    failure_kind=failure_kind or (classify_failure(task.last_error_message) if run_status == "failed" else None),
                    backoff_active=backoff_active,
                    next_retry_at=next_retry_at,
                    is_stale=is_stale,
                    last_success_at=last_success_at,
                )
            )
        return DashboardCollectionHealth(
            status=status,
            monitored_task_count=len(enabled_tasks),
            failed_task_count=len(failed_tasks),
            partial_task_count=len(partial_tasks),
            stale_task_count=len(stale_tasks),
            backoff_task_count=backoff_count,
            last_success_at=max(successful_at) if successful_at else None,
            failed_sources=[task.name for task in failed_tasks],
            partial_sources=[task.name for task in partial_tasks],
            issues=issues,
        )


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _collection_issue_reason(*, status: str, raw_error: str | None, is_stale: bool) -> str:
    text = (raw_error or "").strip()
    normalized = text.lower()
    if normalized == "network_unreachable":
        return "网络无法连接（network_unreachable）"
    if normalized.startswith("run completed with partial failures"):
        return "本次仅完成部分采集；已成功内容仍已保存，请查看任务日志确认失败项。"
    if "timeout" in normalized or "timed out" in normalized:
        return "请求超时：" + text
    if "403" in normalized:
        return "目标网站拒绝访问（HTTP 403）"
    if "429" in normalized:
        return "目标网站请求过于频繁（HTTP 429）"
    if "captcha" in normalized or "验证码" in text:
        return "目标网站触发验证码或访问校验"
    if "err_connection_closed" in normalized or "connection closed" in normalized:
        return (
            "目标网站连接被中断（ERR_CONNECTION_CLOSED）；"
            "请检查本机代理、TUN 分流或公司网络出口。"
        )
    if "err_http_response_code_failure" in normalized:
        return "目标网站返回异常 HTTP 响应；请检查网络分流或网站是否暂时不可用。"
    if text:
        return text[:500]
    if status == "partial":
        return "本次仅完成部分采集；已成功内容仍已保存，请查看任务日志确认失败项。"
    if status == "failed":
        return "本次采集失败；任务未记录更具体的错误，请查看系统日志。"
    if is_stale:
        return "超过 24 小时未成功更新，请检查定时任务或手动重跑。"
    return "采集状态异常，请查看系统日志。"
