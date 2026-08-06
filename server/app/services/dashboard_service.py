from app.core.runtime_status import get_runtime_snapshot
from app.repositories.data_repo import DataRepository
from app.repositories.keyword_rule_repo import KeywordRepository
from app.repositories.task_repo import TaskRepository
from app.schemas.dashboard import (
    DashboardMetrics,
    DashboardOverview,
    DashboardRuntime,
    KeywordHeatItem,
    ProjectSignalItem,
    SourceDistributionItem,
)
from app.services.notice_service import NoticeService


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

        recent_notices = [
            self.notice_service._to_notice_list_item(item, active_kws, high_pri_kws) for item in recent_items[:5]
        ]
        high_value_notices = [
            self.notice_service._to_notice_list_item(item, active_kws, high_pri_kws) for item in high_priority_items
        ]

        async def filtered_total(**filters) -> int:
            _, total = await self.data_repo.list_paginated(
                page=1,
                page_size=1,
                enabled_only=True,
                include_disabled_history=True,
                active_keywords_for_sort=active_kws or None,
                active_keywords_for_filter=active_kws,
                high_priority_keywords=high_pri_kws,
                **filters,
            )
            return total

        today_new_notices = await filtered_total(captured_today=True)
        keyword_hit_notices = await filtered_total(keyword_hit=True)
        high_priority_notices = await filtered_total(high_priority=True)
        high_quality_notices = await filtered_total(high_quality=True)
        project_declaration_notices = await filtered_total(project_signal="申报通知")
        result_publication_notices = await filtered_total(project_signal="结果公示")
        source_counts, source_total = await self.data_repo.aggregate_source_sites(
            enabled_only=True,
            include_disabled_history=True,
        )
        source_options = await self.notice_service.list_source_sites()
        source_display_names = {option.source_site: option.display_name for option in source_options}
        keyword_counts = await self.data_repo.aggregate_keyword_hits(
            active_keywords=active_kws,
            enabled_only=True,
            include_disabled_history=True,
        )
        project_signal_counts = await self.data_repo.aggregate_project_signals(
            enabled_only=True,
            include_disabled_history=True,
        )
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
                today_new_notices=today_new_notices,
                keyword_hit_notices=keyword_hit_notices,
                monitoring_site_count=len(enabled_tasks),
                high_priority_notices=high_priority_notices,
                high_quality_notices=high_quality_notices,
                project_declaration_notices=project_declaration_notices,
                result_publication_notices=result_publication_notices,
            ),
            runtime=runtime,
            high_value_notices=high_value_notices,
            recent_notices=recent_notices,
            keyword_heat=keyword_heat,
            source_distribution=source_distribution,
            project_signal_distribution=project_signal_distribution,
            last_updated_at=last_updated_at,
        )
