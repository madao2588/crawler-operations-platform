from app.utils.notice import (
    effective_active_keywords,
    effective_high_priority_keywords,
    is_high_priority_notice,
    is_high_quality_notice,
    project_notice_has_project_context,
    project_notice_kind,
)


def test_effective_active_keywords_use_enabled_database_rules_only() -> None:
    merged = effective_active_keywords(["招标", "采购", "招标"])
    assert merged == ["招标", "采购"]


def test_effective_active_keywords_empty_rules_stay_empty() -> None:
    assert effective_active_keywords([]) == []


def test_business_priority_and_content_quality_are_independent() -> None:
    business_keywords = effective_high_priority_keywords(["项目申报"])

    assert is_high_quality_notice(quality_score=80) is True
    assert (
        is_high_priority_notice(
            matched_keywords=[],
            high_priority_keywords=business_keywords,
        )
        is False
    )

    assert is_high_quality_notice(quality_score=20) is False
    assert (
        is_high_priority_notice(
            matched_keywords=["项目申报"],
            high_priority_keywords=business_keywords,
        )
        is True
    )

    assert (
        is_high_priority_notice(
            matched_keywords=["会议"],
            high_priority_keywords=business_keywords,
        )
        is False
    )


def test_effective_high_priority_keywords_use_database_rules_only() -> None:
    merged = effective_high_priority_keywords(["重点研发", "项目申报"])

    assert merged == ["重点研发", "项目申报"]


def test_project_notice_kind_splits_declaration_and_result_publication() -> None:
    assert project_notice_kind(["关于组织申报生物医药项目的通知"]) == "申报通知"
    assert project_notice_kind(["科技计划项目拟立项结果公示"]) == "结果公示"
    assert project_notice_kind(["会议报名通知"]) == "其他项目线索"


def test_project_notice_kind_prefers_title_and_understands_official_result_phrases() -> None:
    assert (
        project_notice_kind(
            [
                "关于发布重点研发计划项目申报指南的通知",
                "申报材料将经过形式审查，评审结果和拟入库情况另行通知。",
            ]
        )
        == "申报通知"
    )
    assert (
        project_notice_kind(
            [
                "关于开展2027年度人工智能项目入库储备工作的通知",
                "申报单位请按照申报指南提交材料。",
            ]
        )
        == "申报通知"
    )
    assert project_notice_kind(["关于科技项目审核结果的公示"]) == "结果公示"
    assert project_notice_kind(["关于科技项目验收结论的公示"]) == "结果公示"
    assert project_notice_kind(["2026年科技人才计划支持经费公示"]) == "结果公示"
    assert project_notice_kind(["关于公布重点研发计划立项名单的通知"]) == "结果公示"
    assert project_notice_kind(["关于开展2026年度科技项目验收工作的通知"]) == "其他项目线索"
    assert (
        project_notice_kind(
            [
                "关于发布2027年度揭榜挂帅项目榜单的通知",
                "项目入选后将另行公示拟立项结果。",
            ]
        )
        == "申报通知"
    )
    assert project_notice_kind(["关于生物医药产业临床试验视同立项项目公示"]) == "结果公示"
    assert project_notice_kind(["关于科技型企业拟登记名单的公示"]) == "结果公示"
    assert (
        project_notice_kind(
            [
                "关于开展2026年度科技项目验收工作的通知",
                "验收工作完成后将另行公示验收结果。",
            ]
        )
        == "其他项目线索"
    )


def test_project_notice_context_excludes_meetings_and_competitors_but_allows_project_tasks() -> None:
    assert project_notice_has_project_context(category="项目申报") is True
    assert (
        project_notice_has_project_context(
            category="行业会议",
            metadata={"kind": "industry_meeting"},
            task_name="中国药学会会议信息采集",
        )
        is False
    )
    assert (
        project_notice_has_project_context(
            category="竞品信息",
            metadata={"kind": "competitor_intelligence"},
            task_name="竞品情报采集",
        )
        is False
    )
    assert (
        project_notice_has_project_context(
            category="未分类",
            task_name="科技厅项目申报采集",
        )
        is True
    )


def test_project_notice_kind_requires_project_context_for_signal_keywords() -> None:
    assert (
        project_notice_kind(
            ["某药物申报结果公示"],
            category="竞品信息",
            metadata={"kind": "competitor_intelligence"},
        )
        == "其他项目线索"
    )
    assert (
        project_notice_kind(
            ["关于组织申报创新药项目的通知"],
            category="未分类",
            task_name="科技厅项目申报采集",
        )
        == "申报通知"
    )
