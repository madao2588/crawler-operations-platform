from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import and_, case, desc, false, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data import CollectedData
from app.models.task import Task
from app.utils.notice import (
    NON_PROJECT_NOTICE_CATEGORIES,
    NON_PROJECT_NOTICE_METADATA_KINDS,
    PROJECT_DECLARATION_SIGNAL_KEYWORDS,
    PROJECT_NOTICE_CATEGORIES,
    PROJECT_NOTICE_IRRELEVANCE_KEYWORDS,
    PROJECT_NOTICE_METADATA_KINDS,
    PROJECT_NOTICE_RELEVANCE_CONTEXT_KEYWORDS,
    PROJECT_NOTICE_TASK_KEYWORDS,
    PROJECT_PROCESS_SIGNAL_KEYWORDS,
    PROJECT_RESULT_SIGNAL_KEYWORD_GROUPS,
    PROJECT_RESULT_IRRELEVANCE_KEYWORDS,
    PROJECT_RESULT_SIGNAL_KEYWORDS,
    extract_source_site,
)


SHANGHAI_TIMEZONE = ZoneInfo("Asia/Shanghai")


class DataRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        *,
        task_id: int,
        title: str | None,
        content_html: str | None,
        content_text: str | None,
        source_url: str,
        snapshot_path: str | None,
        quality_score: int,
        content_hash: str | None,
        published_at: datetime | None = None,
        category: str = "未分类",
        ai_summary: str | None = None,
        metadata_json: str | None = None,
    ) -> CollectedData:
        data = CollectedData(
            task_id=task_id,
            title=title,
            content_html=content_html,
            content_text=content_text,
            source_url=source_url,
            snapshot_path=snapshot_path,
            quality_score=quality_score,
            content_hash=content_hash,
            published_at=published_at,
            category=category,
            ai_summary=ai_summary,
            metadata_json=metadata_json,
        )
        self.session.add(data)
        await self.session.commit()
        await self.session.refresh(data)
        return data

    async def get_by_source_url(self, source_url: str) -> CollectedData | None:
        statement = (
            select(CollectedData).where(CollectedData.source_url == source_url).order_by(CollectedData.id.desc())
        )
        result = await self.session.execute(statement)
        return result.scalars().first()

    async def update(self, data: CollectedData, **kwargs) -> CollectedData:
        for k, v in kwargs.items():
            setattr(data, k, v)
        from datetime import datetime, timezone

        data.fetch_time = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(data)
        return data

    async def update_review_metadata(self, data: CollectedData, **kwargs) -> CollectedData:
        for k, v in kwargs.items():
            setattr(data, k, v)
        await self.session.commit()
        await self.session.refresh(data)
        return data

    async def get_by_id(self, data_id: int) -> CollectedData | None:
        statement = select(CollectedData).where(CollectedData.id == data_id)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_by_hash(self, content_hash: str) -> CollectedData | None:
        statement = select(CollectedData).where(CollectedData.content_hash == content_hash)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_paginated(
        self,
        *,
        page: int,
        page_size: int,
        task_id: int | None = None,
        keyword: str | None = None,
        category: str | None = None,
        review_status: str | None = None,
        archived: bool | None = None,
        captured_today: bool | None = None,
        business_today: bool | None = None,
        business_week: bool | None = None,
        month: str | None = None,
        source_site: str | None = None,
        keyword_hit: bool | None = None,
        high_priority: bool | None = None,
        high_quality: bool | None = None,
        project_signal: str | None = None,
        data_ids: set[int] | None = None,
        enabled_only: bool = False,
        include_disabled_history: bool = False,
        active_keywords_for_sort: list[str] | None = None,
        active_keywords_for_filter: list[str] | None = None,
        high_priority_keywords: list[str] | None = None,
        quality_first: bool = False,
    ) -> tuple[Sequence[CollectedData], int]:
        filters, joined_task = _notice_filters(
            task_id=task_id,
            keyword=keyword,
            category=category,
            review_status=review_status,
            archived=archived,
            captured_today=captured_today,
            business_today=business_today,
            business_week=business_week,
            month=month,
            source_site=source_site,
            keyword_hit=keyword_hit,
            high_priority=high_priority,
            high_quality=high_quality,
            project_signal=project_signal,
            data_ids=data_ids,
            enabled_only=enabled_only,
            include_disabled_history=include_disabled_history,
            active_keywords_for_filter=active_keywords_for_filter,
            high_priority_keywords=high_priority_keywords,
        )

        total_statement = select(func.count()).select_from(CollectedData)
        statement = select(CollectedData)
        if joined_task:
            total_statement = total_statement.join(Task, Task.id == CollectedData.task_id)
            statement = statement.join(Task, Task.id == CollectedData.task_id)
        if filters:
            total_statement = total_statement.where(*filters)
        total = await self.session.scalar(total_statement) or 0

        if filters:
            statement = statement.where(*filters)

        sort_keywords: list[str] = []
        if active_keywords_for_sort:
            sort_keywords = [k.strip() for k in active_keywords_for_sort if k and str(k).strip()]

        if quality_first:
            order_cols = [
                desc(CollectedData.quality_score),
                desc(CollectedData.fetch_time),
                desc(CollectedData.id),
            ]
        elif sort_keywords:
            blob = func.lower(
                func.concat(
                    func.coalesce(CollectedData.title, literal("")),
                    literal(" "),
                    func.coalesce(CollectedData.content_text, literal("")),
                )
            )
            hit_exprs = [func.instr(blob, kw.lower()) > 0 for kw in sort_keywords]
            hit_rank = case((or_(*hit_exprs), 1), else_=0)
            order_cols = [desc(hit_rank), desc(CollectedData.fetch_time), desc(CollectedData.id)]
        else:
            order_cols = [desc(CollectedData.fetch_time), desc(CollectedData.id)]

        statement = statement.order_by(*order_cols).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(statement)
        return result.scalars().all(), total

    async def aggregate_notice_months(
        self,
        *,
        keyword: str | None = None,
        category: str | None = None,
        review_status: str | None = None,
        archived: bool | None = None,
        captured_today: bool | None = None,
        business_today: bool | None = None,
        business_week: bool | None = None,
        source_site: str | None = None,
        keyword_hit: bool | None = None,
        high_priority: bool | None = None,
        high_quality: bool | None = None,
        project_signal: str | None = None,
        data_ids: set[int] | None = None,
        enabled_only: bool = False,
        include_disabled_history: bool = False,
        active_keywords_for_filter: list[str] | None = None,
        high_priority_keywords: list[str] | None = None,
    ) -> list[tuple[str, int]]:
        filters, joined_task = _notice_filters(
            keyword=keyword,
            category=category,
            review_status=review_status,
            archived=archived,
            captured_today=captured_today,
            business_today=business_today,
            business_week=business_week,
            source_site=source_site,
            keyword_hit=keyword_hit,
            high_priority=high_priority,
            high_quality=high_quality,
            project_signal=project_signal,
            data_ids=data_ids,
            enabled_only=enabled_only,
            include_disabled_history=include_disabled_history,
            active_keywords_for_filter=active_keywords_for_filter,
            high_priority_keywords=high_priority_keywords,
        )
        business_month = func.strftime(
            "%Y-%m",
            func.datetime(_notice_business_date_expression(), "+8 hours"),
        )
        notice_count = func.count(CollectedData.id)
        statement = select(
            business_month.label("month"),
            notice_count.label("notice_count"),
        ).select_from(CollectedData)
        if joined_task:
            statement = statement.join(Task, Task.id == CollectedData.task_id)
        if filters:
            statement = statement.where(*filters)
        statement = (
            statement.where(business_month.is_not(None))
            .group_by(business_month)
            .order_by(business_month.desc())
        )
        rows = (await self.session.execute(statement)).all()
        return [(str(row.month), int(row.notice_count)) for row in rows]

    async def aggregate_source_sites(
        self,
        *,
        enabled_only: bool = False,
        include_disabled_history: bool = False,
        limit: int = 10,
    ) -> tuple[list[tuple[str, int]], int]:
        filters, joined_task = _notice_filters(
            enabled_only=enabled_only,
            include_disabled_history=include_disabled_history,
        )
        source_site = _source_site_expression()
        notice_count = func.count(CollectedData.id)
        statement = select(source_site.label("source_site"), notice_count.label("notice_count")).select_from(
            CollectedData
        )
        total_statement = select(func.count()).select_from(CollectedData)
        if joined_task:
            statement = statement.join(Task, Task.id == CollectedData.task_id)
            total_statement = total_statement.join(Task, Task.id == CollectedData.task_id)
        if filters:
            statement = statement.where(*filters)
            total_statement = total_statement.where(*filters)
        statement = statement.group_by(source_site).order_by(desc(notice_count), source_site.asc()).limit(limit)
        rows = (await self.session.execute(statement)).all()
        total = await self.session.scalar(total_statement) or 0
        return [(str(row.source_site), int(row.notice_count)) for row in rows], int(total)

    async def aggregate_source_site_task_counts(
        self,
        *,
        enabled_only: bool = False,
        include_disabled_history: bool = False,
    ) -> list[tuple[str, str, int]]:
        filters, _ = _notice_filters(
            enabled_only=enabled_only,
            include_disabled_history=include_disabled_history,
        )
        statement = (
            select(
                CollectedData.source_url,
                Task.name.label("task_name"),
            )
            .select_from(CollectedData)
            .join(Task, Task.id == CollectedData.task_id)
        )
        if filters:
            statement = statement.where(*filters)
        rows = (await self.session.execute(statement)).all()
        counts: defaultdict[tuple[str, str], int] = defaultdict(int)
        for row in rows:
            counts[(extract_source_site(str(row.source_url)), str(row.task_name))] += 1
        return [
            (source_site, task_name, notice_count)
            for (source_site, task_name), notice_count in sorted(counts.items())
        ]

    async def aggregate_dashboard_metrics(
        self,
        *,
        active_keywords: list[str],
        high_priority_keywords: list[str],
    ) -> dict[str, int]:
        filters, _ = _notice_filters(
            enabled_only=True,
            include_disabled_history=True,
        )
        start, end = _shanghai_business_day_utc_bounds()
        expressions = {
            "today_new_notices": and_(
                CollectedData.published_at.is_not(None),
                CollectedData.published_at >= start,
                CollectedData.published_at < end,
            ),
            "keyword_hit_notices": _contains_any(
                _notice_keyword_blob(),
                _normalized_keywords(active_keywords),
            ),
            "high_priority_notices": _contains_any(
                _notice_keyword_blob(),
                _normalized_keywords(high_priority_keywords),
            ),
            "high_quality_notices": CollectedData.quality_score >= 60,
            "project_declaration_notices": _project_signal_expression("申报通知"),
            "result_publication_notices": _project_signal_expression("结果公示"),
            "other_project_notices": _project_signal_expression("其他项目线索"),
        }
        columns = [
            func.coalesce(func.sum(case((expression, 1), else_=0)), 0).label(name)
            for name, expression in expressions.items()
        ]
        statement = (
            select(*columns)
            .select_from(CollectedData)
            .join(Task, Task.id == CollectedData.task_id)
            .where(*filters)
        )
        row = (await self.session.execute(statement)).mappings().one()
        return {name: int(row[name]) for name in expressions}

    async def aggregate_keyword_hits(
        self,
        *,
        active_keywords: list[str],
        enabled_only: bool = False,
        include_disabled_history: bool = False,
        limit: int = 10,
    ) -> list[tuple[str, int]]:
        keywords = _unique_keywords(active_keywords)
        if not keywords:
            return []

        filters, joined_task = _notice_filters(
            enabled_only=enabled_only,
            include_disabled_history=include_disabled_history,
        )
        count_columns = [
            func.coalesce(
                func.sum(case((_keyword_filter_expression(keyword), 1), else_=0)),
                0,
            ).label(f"keyword_{index}")
            for index, keyword in enumerate(keywords)
        ]
        statement = select(*count_columns).select_from(CollectedData)
        if joined_task:
            statement = statement.join(Task, Task.id == CollectedData.task_id)
        if filters:
            statement = statement.where(*filters)
        row = (await self.session.execute(statement)).one()
        counts = [(keyword, int(row[index])) for index, keyword in enumerate(keywords)]
        counts.sort(key=lambda item: (-item[1], keywords.index(item[0])))
        return [item for item in counts if item[1] > 0][:limit]

    async def aggregate_project_signals(
        self,
        *,
        enabled_only: bool = False,
        include_disabled_history: bool = False,
    ) -> list[tuple[str, int]]:
        labels = ("申报通知", "结果公示", "其他项目线索")
        filters, joined_task = _notice_filters(
            enabled_only=enabled_only,
            include_disabled_history=include_disabled_history,
        )
        count_columns = [
            func.coalesce(
                func.sum(case((_project_signal_expression(label), 1), else_=0)),
                0,
            ).label(f"project_signal_{index}")
            for index, label in enumerate(labels)
        ]
        statement = select(*count_columns).select_from(CollectedData).join(Task, Task.id == CollectedData.task_id)
        if filters:
            statement = statement.where(*filters)
        row = (await self.session.execute(statement)).one()
        return [(label, int(row[index])) for index, label in enumerate(labels)]

    async def list_recent_for_export(
        self,
        *,
        task_id: int | None,
        limit: int,
        category: str | None = None,
        review_status: str | None = None,
        archived: bool | None = None,
    ) -> Sequence[CollectedData]:
        statement = select(CollectedData).where(_relevant_notice_expression())
        if task_id is not None:
            statement = statement.where(CollectedData.task_id == task_id)
        if category:
            statement = statement.where(CollectedData.category == category)
        if review_status:
            statement = statement.where(CollectedData.review_status == review_status)
        if archived is not None:
            statement = statement.where(CollectedData.is_archived.is_(archived))
        statement = statement.order_by(CollectedData.id.desc()).limit(limit)
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def update_snapshot_path(
        self,
        *,
        data: CollectedData,
        snapshot_path: str,
    ) -> CollectedData:
        data.snapshot_path = snapshot_path
        await self.session.commit()
        await self.session.refresh(data)
        return data

    async def count_all(self) -> int:
        statement = select(func.count()).select_from(CollectedData)
        return await self.session.scalar(statement) or 0

    async def count_today(self, *, enabled_only: bool = False) -> int:
        start, end = _shanghai_business_day_utc_bounds()
        statement = select(func.count()).select_from(CollectedData)
        if enabled_only:
            statement = statement.join(Task, Task.id == CollectedData.task_id)
        statement = statement.where(
            CollectedData.fetch_time >= start,
            CollectedData.fetch_time < end,
        )
        if enabled_only:
            statement = statement.where(
                Task.status == 1,
                CollectedData.source_url != Task.start_url,
            )
        return await self.session.scalar(statement) or 0

    async def average_quality_score(self) -> float:
        statement = select(func.avg(CollectedData.quality_score))
        average = await self.session.scalar(statement)
        return float(average or 0.0)


def _normalized_keywords(keywords: list[str] | None) -> list[str]:
    return [keyword.strip().lower() for keyword in keywords or [] if keyword and keyword.strip()]


def _unique_keywords(keywords: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw_keyword in keywords:
        keyword = raw_keyword.strip()
        normalized = keyword.lower()
        if not keyword or normalized in seen:
            continue
        seen.add(normalized)
        result.append(keyword)
    return result


def _notice_keyword_blob():
    return func.lower(
        func.concat(
            func.coalesce(CollectedData.title, literal("")),
            literal(" "),
            func.coalesce(CollectedData.content_text, literal("")),
        )
    )


def _project_signal_blob():
    return func.lower(
        func.concat(
            func.coalesce(CollectedData.title, literal("")),
            literal(" "),
            func.coalesce(CollectedData.content_text, literal("")),
            literal(" "),
            func.coalesce(CollectedData.ai_summary, literal("")),
        )
    )


def _project_supporting_signal_blob():
    return func.lower(
        func.concat(
            func.coalesce(CollectedData.content_text, literal("")),
            literal(" "),
            func.coalesce(CollectedData.ai_summary, literal("")),
        )
    )


def _json_extract_text(column, path: str):
    return case(
        (
            and_(column.is_not(None), func.json_valid(column) == 1),
            func.coalesce(func.json_extract(column, path), literal("")),
        ),
        else_=literal(""),
    )


def _task_name_blob():
    return func.lower(func.coalesce(Task.name, literal("")))


def _project_notice_context_expression():
    metadata_kind = func.lower(_json_extract_text(CollectedData.metadata_json, "$.kind"))
    task_category = _json_extract_text(Task.parser_rules, "$.category")
    project_task_keywords = _normalized_keywords(list(PROJECT_NOTICE_TASK_KEYWORDS))
    non_project_expression = or_(
        CollectedData.category.in_(NON_PROJECT_NOTICE_CATEGORIES),
        metadata_kind.in_(NON_PROJECT_NOTICE_METADATA_KINDS),
        task_category.in_(NON_PROJECT_NOTICE_CATEGORIES),
    )
    return and_(
        ~non_project_expression,
        or_(
            CollectedData.category.in_(PROJECT_NOTICE_CATEGORIES),
            metadata_kind.in_(PROJECT_NOTICE_METADATA_KINDS),
            task_category.in_(PROJECT_NOTICE_CATEGORIES),
            _contains_any(_task_name_blob(), project_task_keywords),
        ),
    )


def _stored_project_notice_context_expression():
    metadata_kind = func.lower(
        _json_extract_text(CollectedData.metadata_json, "$.kind")
    )
    non_project_expression = or_(
        CollectedData.category.in_(NON_PROJECT_NOTICE_CATEGORIES),
        metadata_kind.in_(NON_PROJECT_NOTICE_METADATA_KINDS),
    )
    return and_(
        ~non_project_expression,
        or_(
            CollectedData.category.in_(PROJECT_NOTICE_CATEGORIES),
            metadata_kind.in_(PROJECT_NOTICE_METADATA_KINDS),
        ),
    )


def _relevant_notice_expression():
    project_context = _stored_project_notice_context_expression()
    positive_context = _contains_any(
        _project_signal_blob(),
        _normalized_keywords(list(PROJECT_NOTICE_RELEVANCE_CONTEXT_KEYWORDS)),
    )
    title_blob = func.lower(func.coalesce(CollectedData.title, literal("")))
    excluded_context = _contains_any(
        title_blob,
        _normalized_keywords(list(PROJECT_NOTICE_IRRELEVANCE_KEYWORDS)),
    )
    return or_(~project_context, and_(positive_context, ~excluded_context))


def _contains_any(blob, keywords: list[str]):
    if not keywords:
        return literal(False)
    return or_(*(func.instr(blob, keyword) > 0 for keyword in keywords))


def _contains_all_groups(blob, keyword_groups: tuple[tuple[str, ...], ...]):
    if not keyword_groups:
        return literal(False)
    return or_(
        *(
            and_(*(func.instr(blob, keyword.lower()) > 0 for keyword in group))
            for group in keyword_groups
        )
    )


def _project_result_signal_expression(blob):
    return and_(
        ~_contains_any(
            blob,
            _normalized_keywords(list(PROJECT_RESULT_IRRELEVANCE_KEYWORDS)),
        ),
        or_(
            _contains_any(
                blob,
                _normalized_keywords(list(PROJECT_RESULT_SIGNAL_KEYWORDS)),
            ),
            _contains_all_groups(blob, PROJECT_RESULT_SIGNAL_KEYWORD_GROUPS),
        ),
    )


def _keyword_filter_expression(keyword: str):
    normalized = keyword.strip().lower()
    if not normalized:
        return literal(False)
    return func.instr(_notice_keyword_blob(), normalized) > 0


def _project_signal_expression(project_signal: str):
    title_blob = func.lower(func.coalesce(CollectedData.title, literal("")))
    supporting_blob = _project_supporting_signal_blob()
    project_context_expression = _project_notice_context_expression()
    title_declaration_expression = _contains_any(
        title_blob,
        _normalized_keywords(list(PROJECT_DECLARATION_SIGNAL_KEYWORDS)),
    )
    title_result_expression = _project_result_signal_expression(title_blob)
    title_result_excluded_expression = _contains_any(
        title_blob,
        _normalized_keywords(list(PROJECT_RESULT_IRRELEVANCE_KEYWORDS)),
    )
    title_process_expression = _contains_any(
        title_blob,
        _normalized_keywords(list(PROJECT_PROCESS_SIGNAL_KEYWORDS)),
    )
    supporting_declaration_expression = _contains_any(
        supporting_blob,
        _normalized_keywords(list(PROJECT_DECLARATION_SIGNAL_KEYWORDS)),
    )
    supporting_result_expression = _project_result_signal_expression(
        supporting_blob
    )
    result_expression = and_(
        ~title_result_excluded_expression,
        or_(
            title_result_expression,
            and_(
                ~title_result_expression,
                ~title_declaration_expression,
                ~title_process_expression,
                supporting_result_expression,
            ),
        ),
    )
    declaration_expression = and_(
        ~title_result_excluded_expression,
        or_(
            and_(~title_result_expression, title_declaration_expression),
            and_(
                ~title_result_expression,
                ~title_declaration_expression,
                ~title_process_expression,
                ~supporting_result_expression,
                supporting_declaration_expression,
            ),
        ),
    )
    if project_signal == "结果公示":
        return and_(project_context_expression, result_expression)
    if project_signal == "申报通知":
        return and_(project_context_expression, declaration_expression, ~result_expression)
    if project_signal == "其他项目线索":
        return and_(
            project_context_expression,
            ~declaration_expression,
            ~result_expression,
        )
    return literal(False)


def _source_site_expression():
    source_url = func.lower(func.coalesce(CollectedData.source_url, literal("")))
    scheme_separator = func.instr(source_url, "://")
    after_scheme = case(
        (scheme_separator > 0, func.substr(source_url, scheme_separator + 3)),
        else_=literal(""),
    )
    slash_position = func.instr(after_scheme, "/")
    authority = case(
        (slash_position > 0, func.substr(after_scheme, 1, slash_position - 1)),
        else_=after_scheme,
    )
    at_position = func.instr(authority, "@")
    host_and_port = case(
        (at_position > 0, func.substr(authority, at_position + 1)),
        else_=authority,
    )
    bracket_end = func.instr(host_and_port, "]")
    port_separator = func.instr(host_and_port, ":")
    hostname = case(
        (
            and_(func.substr(host_and_port, 1, 1) == "[", bracket_end > 1),
            func.substr(host_and_port, 2, bracket_end - 2),
        ),
        (port_separator > 0, func.substr(host_and_port, 1, port_separator - 1)),
        else_=host_and_port,
    )
    without_www = case(
        (func.substr(hostname, 1, 4) == "www.", func.substr(hostname, 5)),
        else_=hostname,
    )
    return case((without_www != "", without_www), else_=literal("unknown"))


def _notice_filters(
    *,
    task_id: int | None = None,
    keyword: str | None = None,
    category: str | None = None,
    review_status: str | None = None,
    archived: bool | None = None,
    captured_today: bool | None = None,
    business_today: bool | None = None,
    business_week: bool | None = None,
    month: str | None = None,
    source_site: str | None = None,
    keyword_hit: bool | None = None,
    high_priority: bool | None = None,
    high_quality: bool | None = None,
    project_signal: str | None = None,
    data_ids: set[int] | None = None,
    enabled_only: bool = False,
    include_disabled_history: bool = False,
    active_keywords_for_filter: list[str] | None = None,
    high_priority_keywords: list[str] | None = None,
) -> tuple[list, bool]:
    filters = [_relevant_notice_expression()]
    requires_task_join = enabled_only
    if task_id is not None:
        filters.append(CollectedData.task_id == task_id)
    if keyword:
        filters.append(_keyword_filter_expression(keyword))
    if category:
        filters.append(CollectedData.category == category)
    if review_status:
        filters.append(CollectedData.review_status == review_status)
    if archived is not None:
        filters.append(CollectedData.is_archived.is_(archived))
    if captured_today is not None:
        start, end = _shanghai_business_day_utc_bounds()
        captured_on_today = and_(
            CollectedData.fetch_time >= start,
            CollectedData.fetch_time < end,
        )
        filters.append(captured_on_today if captured_today else ~captured_on_today)
    if business_today is not None:
        start, end = _shanghai_business_day_utc_bounds()
        business_on_today = and_(
            CollectedData.published_at.is_not(None),
            CollectedData.published_at >= start,
            CollectedData.published_at < end,
        )
        filters.append(business_on_today if business_today else ~business_on_today)
    if business_week is not None:
        start, end = _shanghai_business_week_utc_bounds()
        business_in_week = and_(
            CollectedData.published_at.is_not(None),
            CollectedData.published_at >= start,
            CollectedData.published_at < end,
        )
        filters.append(business_in_week if business_week else ~business_in_week)
    if month:
        start, end = _shanghai_business_month_utc_bounds(month)
        business_date = _notice_business_date_expression()
        filters.append(and_(business_date >= start, business_date < end))
    if source_site:
        normalized_site = source_site.strip().lower().removeprefix("www.")
        filters.append(_source_site_expression() == normalized_site)

    active_filter_keywords = _normalized_keywords(active_keywords_for_filter)
    keyword_expression = _contains_any(_notice_keyword_blob(), active_filter_keywords)
    if keyword_hit is not None:
        filters.append(keyword_expression if keyword_hit else ~keyword_expression)

    priority_expression = _contains_any(
        _notice_keyword_blob(),
        _normalized_keywords(high_priority_keywords or []),
    )
    if high_priority is not None:
        filters.append(priority_expression if high_priority else ~priority_expression)

    high_quality_expression = CollectedData.quality_score >= 60
    if high_quality is not None:
        filters.append(high_quality_expression if high_quality else ~high_quality_expression)

    if project_signal:
        filters.append(_project_signal_expression(project_signal))
        requires_task_join = True

    if data_ids is not None:
        filters.append(CollectedData.id.in_(data_ids) if data_ids else false())

    if enabled_only and not include_disabled_history:
        filters.append(Task.status == 1)
    if enabled_only:
        filters.append(CollectedData.source_url != Task.start_url)
    return filters, requires_task_join


def _shanghai_business_day_utc_bounds() -> tuple[datetime, datetime]:
    business_date = datetime.now(timezone.utc).astimezone(SHANGHAI_TIMEZONE).date()
    start_local = datetime.combine(business_date, time.min, tzinfo=SHANGHAI_TIMEZONE)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _shanghai_business_week_utc_bounds() -> tuple[datetime, datetime]:
    now_local = datetime.now(timezone.utc).astimezone(SHANGHAI_TIMEZONE)
    start_date = now_local.date() - timedelta(days=now_local.weekday())
    end_date = now_local.date() + timedelta(days=1)
    start_local = datetime.combine(start_date, time.min, tzinfo=SHANGHAI_TIMEZONE)
    end_local = datetime.combine(end_date, time.min, tzinfo=SHANGHAI_TIMEZONE)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _notice_business_date_expression():
    return func.coalesce(CollectedData.published_at, CollectedData.fetch_time)


def _shanghai_business_month_utc_bounds(month: str) -> tuple[datetime, datetime]:
    try:
        year_text, month_text = month.split("-", maxsplit=1)
        year = int(year_text)
        month_number = int(month_text)
        start_local = datetime(year, month_number, 1, tzinfo=SHANGHAI_TIMEZONE)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid notice month: {month}") from exc
    if month_number == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=SHANGHAI_TIMEZONE)
    else:
        end_local = datetime(year, month_number + 1, 1, tzinfo=SHANGHAI_TIMEZONE)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
