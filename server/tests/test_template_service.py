import json

import pytest

from app.repositories.template_repo import TemplateRepository
from app.schemas.template import TaskTemplateCreate
from app.services.template_service import (
    MEETING_ENABLED_TEMPLATE_IDS,
    MEETING_SOURCE_TEMPLATE_IDS,
    NEW_DRUG_SOURCE_TEMPLATES,
    PROJECT_DECLARATION_ENABLED_TEMPLATE_IDS,
    PROJECT_DECLARATION_SOURCE_TEMPLATE_IDS,
    TemplateService,
)


@pytest.mark.asyncio
async def test_ensure_seed_data_imports_legacy_json(async_session, tmp_path) -> None:
    legacy_file = tmp_path / "task_templates.json"
    legacy_file.write_text(
        json.dumps(
            [
                {
                    "id": "legacy_template",
                    "label": "Legacy Template",
                    "name": "Legacy Name",
                    "start_url": "https://example.com/legacy",
                    "cron_expr": "0 * * * *",
                    "parser_rules": None,
                    "enabled": True,
                    "description": "Imported from legacy JSON storage.",
                    "tags": ["legacy"],
                    "usage_count": 3,
                    "last_used_at": "2026-04-21T06:30:00+00:00",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    service = TemplateService(
        template_repo=TemplateRepository(async_session),
        template_file=legacy_file,
    )

    await service.ensure_seed_data()
    templates = await service.list_task_templates()

    assert len(templates) == 1
    assert templates[0].id == "legacy_template"
    assert templates[0].usage_count == 3
    assert templates[0].tags == ["legacy"]
    assert templates[0].last_used_at is not None


@pytest.mark.asyncio
async def test_ensure_seed_data_adds_missing_seed_when_database_not_empty(async_session, tmp_path) -> None:
    legacy_file = tmp_path / "task_templates.json"
    legacy_file.write_text(
        json.dumps(
            [
                {
                    "id": "legacy_template",
                    "label": "Legacy Template",
                    "name": "Legacy Name",
                    "start_url": "https://example.com/legacy",
                    "cron_expr": "0 * * * *",
                    "parser_rules": None,
                    "enabled": True,
                    "description": "Imported from legacy JSON storage.",
                    "tags": ["legacy"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    service = TemplateService(
        template_repo=TemplateRepository(async_session),
        template_file=legacy_file,
    )
    created = await service.create_task_template(
        TaskTemplateCreate(
            id="existing_template",
            label="Existing Template",
            name="Existing Name",
            start_url="https://example.com/existing",
            cron_expr="15 * * * *",
            parser_rules=None,
            enabled=True,
            description="Already stored in the database.",
            tags=["existing"],
        )
    )
    assert created.id == "existing_template"

    await service.ensure_seed_data()
    templates = await service.list_task_templates()

    assert {template.id for template in templates} == {"existing_template", "legacy_template"}


@pytest.mark.asyncio
async def test_default_seed_data_covers_required_new_drug_sources(async_session, tmp_path) -> None:
    missing_file = tmp_path / "missing_task_templates.json"
    service = TemplateService(
        template_repo=TemplateRepository(async_session),
        template_file=missing_file,
    )

    await service.ensure_seed_data()
    templates = await service.list_task_templates()
    ids = {template.id for template in templates}

    for item in NEW_DRUG_SOURCE_TEMPLATES:
        assert item["id"] in ids


@pytest.mark.asyncio
async def test_default_seed_preserves_operator_edits_and_explicit_sync_restores_contract(
    async_session,
    tmp_path,
) -> None:
    missing_file = tmp_path / "missing_task_templates.json"
    service = TemplateService(
        template_repo=TemplateRepository(async_session),
        template_file=missing_file,
    )
    canonical = next(
        item
        for item in NEW_DRUG_SOURCE_TEMPLATES
        if item["id"] == "most_project_declaration"
    )
    await service.create_task_template(
        TaskTemplateCreate(
            id=str(canonical["id"]),
            label="人工维护的科技部来源",
            name="人工维护的科技部来源",
            start_url="https://example.com/operator-maintained",
            cron_expr="15 6 * * *",
            parser_rules=None,
            enabled=False,
            description="运维人员保存的本地配置。",
            tags=["人工配置"],
        )
    )

    await service.ensure_seed_data()
    preserved = next(
        item
        for item in await service.list_task_templates()
        if item.id == canonical["id"]
    )
    assert preserved.start_url == "https://example.com/operator-maintained"
    assert preserved.enabled is False
    assert preserved.tags == ["人工配置"]

    await service.sync_required_source_templates()
    synchronized = next(
        item
        for item in await service.list_task_templates()
        if item.id == canonical["id"]
    )
    assert synchronized.start_url == canonical["start_url"]
    assert synchronized.enabled == canonical["enabled"]
    assert synchronized.tags == canonical["tags"]


def test_all_government_project_sources_are_enabled_for_requirement_one() -> None:
    enabled_ids = {
        item["id"]
        for item in NEW_DRUG_SOURCE_TEMPLATES
        if item["id"] in PROJECT_DECLARATION_SOURCE_TEMPLATE_IDS
        and item["enabled"]
    }

    assert enabled_ids == PROJECT_DECLARATION_ENABLED_TEMPLATE_IDS
    assert enabled_ids < PROJECT_DECLARATION_SOURCE_TEMPLATE_IDS
    assert enabled_ids == {
        "most_project_declaration",
        "guangdong_stc_notices",
        "guangzhou_sti_notices",
        "huangpu_sti_notices",
        "hengqin_announcements",
        "hunan_stc_notices",
        "changsha_sti_notices",
    }


def test_later_requirement_lanes_are_seeded_with_only_implemented_sources_enabled() -> None:
    later_lane_ids = {
        item["id"]
        for item in NEW_DRUG_SOURCE_TEMPLATES
        if item["id"] not in PROJECT_DECLARATION_SOURCE_TEMPLATE_IDS
    }

    assert later_lane_ids
    enabled_later_lane_ids = {
        item["id"]
        for item in NEW_DRUG_SOURCE_TEMPLATES
        if item["id"] in later_lane_ids and item["enabled"] is True
    }
    assert enabled_later_lane_ids == {
        "pubmed_literature",
        "clinical_trials_competitor",
        *MEETING_ENABLED_TEMPLATE_IDS,
    }


def test_most_source_uses_application_notice_list_not_template_downloads() -> None:
    most = next(
        item
        for item in NEW_DRUG_SOURCE_TEMPLATES
        if item["id"] == "most_project_declaration"
    )
    rules = json.loads(most["parser_rules"])

    assert rules["list_page_urls"] == [
        "https://service.most.gov.cn/kjjh_tztg/",
        "https://service.most.gov.cn/sbtz_new/",
    ]
    assert rules["list_url_template"] == (
        "https://service.most.gov.cn/kjjh_tztg/index_{page}.html"
    )
    assert rules["list_page_from"] == 2
    assert rules["list_page_to"] == 10
    assert rules["max_list_pages"] == 11
    assert rules["max_items"] == 110
    assert "https://service.most.gov.cn/sbwj_new/" not in rules["list_page_urls"]


def test_requirement_one_government_sources_use_site_specific_contracts() -> None:
    expected = {
        "most_project_declaration": {
            "start_url": "https://service.most.gov.cn/kjjh_tztg/",
            "list_item": "td.table_gkgs_title",
        },
        "guangdong_stc_notices": {
            "start_url": "https://gdstc.gd.gov.cn/zwgk_n/tzgg/index.html",
            "list_item": ".list li",
        },
        "guangzhou_sti_notices": {
            "start_url": "https://kjj.gz.gov.cn/xxgk/kjglhxmjf/",
            "list_item": ".news_list li",
        },
        "huangpu_sti_notices": {
            "start_url": "https://www.hp.gov.cn/gzjg/qzfgwhgzbm/qkxjsj/tzgg/index.html",
            "list_item": ".infoList li",
        },
        "hengqin_announcements": {
            "start_url": "https://www.hengqin.gov.cn/macao_zh_hans/zwgk/tzgg/gg/?page=1",
            "list_item": ".app-list__notices li",
        },
        "hunan_stc_notices": {
            "start_url": "http://kjt.hunan.gov.cn/kjt/xxgk/tzgg/index.html",
            "list_item": "#con_two_1 li",
        },
        "changsha_sti_notices": {
            "start_url": "http://kjj.changsha.gov.cn/zfxxgk/tzgg_27202/",
            "list_item": ".list_ul li",
        },
    }
    templates = {str(item["id"]): item for item in NEW_DRUG_SOURCE_TEMPLATES}

    for source_id, contract in expected.items():
        template = templates[source_id]
        rules = json.loads(template["parser_rules"])
        assert template["start_url"] == contract["start_url"]
        assert rules["crawl_mode"] == "list_follow"
        assert rules["list_item"] == contract["list_item"]
        assert rules["list_item"] != "a"
        assert rules["title"].startswith("css:")
        assert rules["content"].startswith("css:")
        assert rules["published_at"].startswith("css:")
        assert rules["category"] == "项目申报"
        assert rules["metadata"]["kind"] == "project_notice"
        assert "申报通知" in template["tags"]
        assert "结果公示" in template["tags"]
        assert "申报" in rules["detail_include_keywords"]
        assert "公示" in rules["detail_include_keywords"]
        assert "项目" in rules["detail_required_context_keywords"]
        assert "研发" in rules["detail_required_context_keywords"]
        assert "录取" in rules["detail_exclude_keywords"]
        assert "招生" in rules["detail_exclude_keywords"]

    hengqin_rules = json.loads(templates["hengqin_announcements"]["parser_rules"])
    assert hengqin_rules["list_page_urls_only"] is True
    assert hengqin_rules["list_page_urls"] == [
        "https://www.hengqin.gov.cn/postmeta/i/24471.json",
        "https://www.hengqin.gov.cn/postmeta/i/24472.json",
    ]
    assert hengqin_rules["list_json_items"] == "articles"
    assert hengqin_rules["list_json_url_field"] == "url"
    assert hengqin_rules["list_json_title_field"] == "title"
    assert "force_dynamic_fetch" not in hengqin_rules
    guangdong_rules = json.loads(templates["guangdong_stc_notices"]["parser_rules"])
    assert "force_dynamic_fetch" not in guangdong_rules
    assert guangdong_rules["embedded_content_url"] == "iframe.yjzj-iframe@src"
    assert guangdong_rules["embedded_content_json_assignment"] == "question_data"
    assert guangdong_rules["embedded_content_json_path"] == "article.content"
    hunan_rules = json.loads(templates["hunan_stc_notices"]["parser_rules"])
    assert hunan_rules["prefer_list_title"] is True
    assert "#zoomcon" in hunan_rules["content"]


def test_wechat_sources_are_manual_only_with_explicit_host_allowlist() -> None:
    wechat_ids = {
        "wechat_k_innovation",
        "wechat_hengqin_biomed",
        "wechat_competitor_intelligence",
        "wechat_industry_meetings",
    }
    templates = {
        str(item["id"]): item
        for item in NEW_DRUG_SOURCE_TEMPLATES
        if item["id"] in wechat_ids
    }

    assert set(templates) == wechat_ids
    for template in templates.values():
        rules = json.loads(template["parser_rules"])
        assert template["enabled"] is False
        assert rules["collection_mode"] == "manual"
        assert rules["allowed_hosts"] == ["mp.weixin.qq.com"]
        assert rules["title"] == "css:#activity-name, h1.rich_media_title"
        assert rules["content"] == "css:#js_content"
        assert rules["published_at"] == "css:#publish_time"

    meeting_rules = json.loads(templates["wechat_industry_meetings"]["parser_rules"])
    assert meeting_rules["category"] == "行业会议"
    assert meeting_rules["metadata"]["kind"] == "industry_meeting"


def test_industry_meeting_templates_expose_executable_or_explicitly_blocked_contracts() -> None:
    templates = {
        item["id"]: item
        for item in NEW_DRUG_SOURCE_TEMPLATES
        if item["id"]
        in {
            "dxy_pharmacy_meetings",
            "cpa_association",
            "bioon_meetings",
            "cphi_china_events",
            "wechat_industry_meetings",
        }
    }

    assert set(templates) == {
        "dxy_pharmacy_meetings",
        "cpa_association",
        "bioon_meetings",
        "cphi_china_events",
        "wechat_industry_meetings",
    }

    dxy_rules = json.loads(templates["dxy_pharmacy_meetings"]["parser_rules"])
    cpa_rules = json.loads(templates["cpa_association"]["parser_rules"])
    cphi_rules = json.loads(templates["cphi_china_events"]["parser_rules"])

    assert dxy_rules["crawl_mode"] == "list_follow"
    assert dxy_rules["metadata"]["kind"] == "industry_meeting"
    assert cpa_rules["crawl_mode"] == "list_follow"
    assert cpa_rules["metadata"]["kind"] == "industry_meeting"
    assert cpa_rules["detail_include_keywords"] == ["do=info"]
    assert "do=infolist" in cpa_rules["detail_exclude_keywords"]
    assert cphi_rules["crawl_mode"] == "meeting_table"
    assert templates["dxy_pharmacy_meetings"]["enabled"] is False
    assert templates["cpa_association"]["enabled"] is True
    assert templates["cphi_china_events"]["enabled"] is True

    bioon_rules = json.loads(templates["bioon_meetings"]["parser_rules"])
    assert bioon_rules["collection_mode"] == "intermittent"
    assert "anti_bot_challenge_keywords" not in bioon_rules
    assert bioon_rules["anti_bot_valid_selector"] == (
        ".meeting-list-item, .banner-text h1"
    )
    assert bioon_rules["request_timeout_sec"] == 25
    assert bioon_rules["detail_retries"] == 0
    assert templates["bioon_meetings"]["enabled"] is True
    assert "验证码" in templates["bioon_meetings"]["description"]


def test_requirement_three_sources_have_executable_and_authorized_contracts() -> None:
    templates = {str(item["id"]): item for item in NEW_DRUG_SOURCE_TEMPLATES}

    pubmed = templates["pubmed_literature"]
    pubmed_rules = json.loads(pubmed["parser_rules"])
    assert pubmed["enabled"] is True
    assert pubmed["start_url"] == "https://pubmed.ncbi.nlm.nih.gov/"
    assert pubmed_rules["crawl_mode"] == "pubmed"
    assert pubmed_rules["max_results_per_topic"] == 25
    assert pubmed_rules["lookback_days"] == 730
    assert [topic["name"] for topic in pubmed_rules["topics"]] == [
        "脑胶质瘤",
        "降尿酸药物",
    ]
    assert "glioma" in pubmed_rules["topics"][0]["query"].lower()
    assert "hyperuricemia" in pubmed_rules["topics"][1]["query"].lower()

    clinical_trials = templates["clinical_trials_competitor"]
    clinical_trials_rules = json.loads(clinical_trials["parser_rules"])
    assert clinical_trials["enabled"] is True
    assert clinical_trials["start_url"] == "https://clinicaltrials.gov/search"
    assert clinical_trials_rules["crawl_mode"] == "clinical_trials"
    assert clinical_trials_rules["max_results_per_topic"] == 25
    assert [topic["name"] for topic in clinical_trials_rules["topics"]] == [
        "脑胶质瘤",
        "降尿酸药物",
    ]
    assert clinical_trials_rules["topics"][0]["condition_query"] == (
        "Glioma OR Glioblastoma"
    )
    assert clinical_trials_rules["topics"][1]["condition_query"] == (
        "Hyperuricemia OR Gout"
    )
    assert all(
        topic["intervention_type"] == "DRUG"
        for topic in clinical_trials_rules["topics"]
    )

    pharnexcloud = templates["pharnexcloud_drug_database"]
    assert pharnexcloud["start_url"] == "https://vip.pharnexcloud.com/database/research"
    assert pharnexcloud["enabled"] is False
    assert pharnexcloud["parser_rules"] is None

    wechat = templates["wechat_competitor_intelligence"]
    assert wechat["enabled"] is False
    assert "竞品信息" in wechat["tags"]
    wechat_rules = json.loads(wechat["parser_rules"])
    assert wechat_rules["category"] == "竞品信息"
    assert wechat_rules["metadata"]["kind"] == "competitor_intelligence"
    assert wechat_rules["metadata"]["source"] == "WeChat"


def test_requirement_two_meeting_sources_use_site_specific_contracts() -> None:
    templates = {str(item["id"]): item for item in NEW_DRUG_SOURCE_TEMPLATES}

    assert MEETING_SOURCE_TEMPLATE_IDS == frozenset(
        {
            "dxy_pharmacy_meetings",
            "cpa_association",
            "bioon_meetings",
            "cphi_china_events",
            "wechat_industry_meetings",
        }
    )
    assert MEETING_ENABLED_TEMPLATE_IDS <= MEETING_SOURCE_TEMPLATE_IDS

    cpa = templates["cpa_association"]
    cpa_rules = json.loads(cpa["parser_rules"])
    assert cpa["enabled"] is True
    assert cpa["start_url"] == "https://www.cpa.org.cn/?classid=270&do=infolist"
    assert cpa_rules["crawl_mode"] == "list_follow"
    assert cpa_rules["list_item"] == "#clist li"
    assert cpa_rules["detail_link"] == ":scope a@href"
    assert cpa_rules["category"] == "行业会议"
    assert cpa_rules["metadata"]["kind"] == "industry_meeting"
    assert cpa_rules["detail_include_keywords"] == ["do=info"]
    assert cpa_rules["detail_exclude_keywords"] == ["do=infolist", "page="]

    bioon = templates["bioon_meetings"]
    bioon_rules = json.loads(bioon["parser_rules"])
    assert bioon["start_url"] == "https://www.bioon.com/meeting/newest"
    assert bioon["enabled"] is True
    assert bioon_rules["crawl_mode"] == "list_follow"
    assert bioon_rules["collection_mode"] == "intermittent"
    assert bioon_rules["list_item"] == ".meeting-list-item"
    assert bioon_rules["detail_link"] == "h2 a@href"
    assert bioon_rules["category"] == "行业会议"
    assert bioon_rules["metadata"]["kind"] == "industry_meeting"

    dxy = templates["dxy_pharmacy_meetings"]
    dxy_rules = json.loads(dxy["parser_rules"])
    assert dxy["enabled"] is False
    assert dxy["start_url"] == "https://meeting.dxy.cn/tag/list/category/pharmacy"
    assert dxy_rules["crawl_mode"] == "list_follow"
    assert dxy_rules["list_item"] == ".x_ct1"
    assert "2024" in dxy_rules["disabled_reason"]

    cphi = templates["cphi_china_events"]
    cphi_rules = json.loads(cphi["parser_rules"])
    assert cphi["enabled"] is True
    assert cphi["start_url"] == "https://www.cphi-china.cn/newconferences/list/"
    assert cphi_rules["crawl_mode"] == "meeting_table"
    assert cphi_rules["category"] == "行业会议"
    assert cphi_rules["meeting_year"] == 2026
