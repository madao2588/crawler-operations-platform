from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from app.repositories.template_repo import TemplateRepository
from app.schemas.template import TaskTemplateCreate, TaskTemplateRead, TaskTemplateUpdate
from app.utils.notice import (
    PROJECT_NOTICE_IRRELEVANCE_KEYWORDS,
    PROJECT_NOTICE_RELEVANCE_CONTEXT_KEYWORDS,
)


DEFAULT_TEMPLATES = [
    {
        "id": "news_article",
        "label": "News Article",
        "name": "News Monitor",
        "start_url": "https://example.com/news",
        "cron_expr": "0 */6 * * *",
        "parser_rules": None,
        "enabled": True,
        "description": "General article pages with readability fallback.",
        "tags": ["readability", "article", "general"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "tender_notice",
        "label": "Tender Notice",
        "name": "Tender Notice Monitor",
        "start_url": "https://example.com/tenders",
        "cron_expr": "0 */2 * * *",
        "parser_rules": '{"title_selector":"h1","content_selector":".article-content"}',
        "enabled": True,
        "description": "Stable detail pages for bidding and procurement notices.",
        "tags": ["tender", "bidding", "detail-page"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "portal_announcement",
        "label": "Portal Announcement",
        "name": "Portal Announcement Monitor",
        "start_url": "https://example.com/announcements",
        "cron_expr": "0 8,12,16 * * *",
        "parser_rules": '{"title_selector":".detail-title","content_selector":".detail-body"}',
        "enabled": True,
        "description": "A good baseline for enterprise or government notice portals.",
        "tags": ["portal", "announcement", "structured"],
        "usage_count": 0,
        "last_used_at": None,
    },
]

PROJECT_DECLARATION_DETAIL_KEYWORDS = [
    "项目",
    "申报",
    "指南",
    "征集",
    "评审",
    "立项",
    "公示",
    "名单",
    "拟支持",
    "补助",
    "资助",
    "奖励",
    "经费",
    "验收",
    "认定",
    "入库",
    "揭榜挂帅",
]

PROJECT_DECLARATION_SOURCE_TEMPLATE_IDS = frozenset(
    {
        "most_project_declaration",
        "guangdong_stc_notices",
        "guangzhou_sti_notices",
        "huangpu_sti_notices",
        "hengqin_announcements",
        "hunan_stc_notices",
        "changsha_sti_notices",
        "wechat_k_innovation",
        "wechat_hengqin_biomed",
    }
)

PROJECT_DECLARATION_ENABLED_TEMPLATE_IDS = frozenset(
    {
        "most_project_declaration",
        "guangdong_stc_notices",
        "guangzhou_sti_notices",
        "huangpu_sti_notices",
        "hengqin_announcements",
        "hunan_stc_notices",
        "changsha_sti_notices",
    }
)

# Curated official pages prove that a fixed source exposes each Requirement 1
# information type even when the current rolling list has no publication of that
# type. These references are validation evidence only; they are not inserted as
# fresh announcements and do not affect normal collection counts.
PROJECT_SIGNAL_CAPABILITY_EVIDENCE = {
    "most_project_declaration": {
        "结果公示": {
            "url": "https://service.most.gov.cn/kjjh_tztg_all/20211209/4758.html",
            "title": "关于国家重点研发计划“储能与智能电网技术”重点专项2021年度拟立项项目安排公示的通知",
        }
    }
}


def _project_parser_rules(
    *,
    list_item: str,
    title: str,
    published_at: str,
    content: str,
    detail_link: str = "a@href",
    list_page_urls: list[str] | None = None,
    list_page_urls_only: bool = False,
    list_url_template: str | None = None,
    list_page_from: int = 1,
    list_page_to: int = 1,
    max_list_pages: int | None = None,
    max_items: int = 20,
    list_json_items: str | None = None,
    list_json_url_field: str | None = None,
    list_json_title_field: str | None = None,
    embedded_content_url: str | None = None,
    embedded_content_json_assignment: str | None = None,
    embedded_content_json_path: str | None = None,
    embedded_content_title_path: str | None = None,
    force_dynamic_fetch: bool = False,
    dynamic_wait_selector: str | None = None,
    prefer_list_title: bool = False,
) -> str:
    rules: dict[str, object] = {
        "crawl_mode": "list_follow",
        "list_item": list_item,
        "detail_link": detail_link,
        "detail_include_keywords": PROJECT_DECLARATION_DETAIL_KEYWORDS,
        "detail_required_context_keywords": list(
            PROJECT_NOTICE_RELEVANCE_CONTEXT_KEYWORDS
        ),
        "detail_exclude_keywords": list(PROJECT_NOTICE_IRRELEVANCE_KEYWORDS),
        "same_host_only": True,
        "max_items": max_items,
        "max_list_pages": max_list_pages or max(1, len(list_page_urls or [])),
        "detail_retries": 1,
        "detail_retry_policy": "transient",
        "request_timeout_sec": 45,
        "title": title,
        "published_at": published_at,
        "content": content,
        "category": "项目申报",
        "metadata": {
            "kind": "project_notice",
            "source_lane": "requirement_1",
        },
    }
    if list_page_urls:
        rules["list_page_urls"] = list_page_urls
    if list_page_urls_only:
        rules["list_page_urls_only"] = True
    if list_url_template:
        rules["list_url_template"] = list_url_template
        rules["list_page_from"] = list_page_from
        rules["list_page_to"] = list_page_to
    if list_json_items:
        rules["list_json_items"] = list_json_items
    if list_json_url_field:
        rules["list_json_url_field"] = list_json_url_field
    if list_json_title_field:
        rules["list_json_title_field"] = list_json_title_field
    if embedded_content_url:
        rules["embedded_content_url"] = embedded_content_url
    if embedded_content_json_assignment:
        rules["embedded_content_json_assignment"] = embedded_content_json_assignment
    if embedded_content_json_path:
        rules["embedded_content_json_path"] = embedded_content_json_path
    if embedded_content_title_path:
        rules["embedded_content_title_path"] = embedded_content_title_path
    if force_dynamic_fetch:
        rules["force_dynamic_fetch"] = True
    if dynamic_wait_selector:
        rules["dynamic_wait_selector"] = dynamic_wait_selector
    if prefer_list_title:
        rules["prefer_list_title"] = True
    return json.dumps(rules, ensure_ascii=False)


MOST_PROJECT_DECLARATION_PARSER_RULES = _project_parser_rules(
    list_page_urls=[
        "https://service.most.gov.cn/kjjh_tztg/",
        "https://service.most.gov.cn/sbtz_new/",
    ],
    list_url_template="https://service.most.gov.cn/kjjh_tztg/index_{page}.html",
    list_page_from=2,
    list_page_to=10,
    max_list_pages=11,
    max_items=110,
    list_item="td.table_gkgs_title",
    detail_link="div@onclick",
    title="css:h1.article__title",
    published_at="css:.article__subTitle",
    content="css:.article-body.section1",
)

GUANGDONG_PROJECT_DECLARATION_PARSER_RULES = _project_parser_rules(
    list_item=".list li",
    detail_link="a@href",
    embedded_content_url="iframe.yjzj-iframe@src",
    embedded_content_json_assignment="question_data",
    embedded_content_json_path="article.content",
    embedded_content_title_path="article.title",
    title="css:h3.zw-title",
    published_at="css:.zw-info .time",
    content="css:.viewList > .zw",
)

GUANGZHOU_PROJECT_DECLARATION_PARSER_RULES = _project_parser_rules(
    list_item=".news_list li",
    title="css:h1.content_title",
    published_at="css:.content_attr",
    content="css:#zoomcon.content_article",
)

HUANGPU_PROJECT_DECLARATION_PARSER_RULES = _project_parser_rules(
    list_item=".infoList li",
    title="css:h1.barrier-free, h1",
    published_at="css:span.article-create_time, .article-info-div",
    content="css:#zhengwen.content",
)

HENGQIN_PROJECT_DECLARATION_PARSER_RULES = _project_parser_rules(
    list_page_urls=[
        "https://www.hengqin.gov.cn/postmeta/i/24471.json",
        "https://www.hengqin.gov.cn/postmeta/i/24472.json",
    ],
    list_page_urls_only=True,
    list_json_items="articles",
    list_json_url_field="url",
    list_json_title_field="title",
    list_item=".app-list__notices li",
    detail_link="a.title@href",
    title="css:.app-content .head h1",
    published_at="css:.app-content .attrs",
    content="css:.app-content .app-common__padding.large .content",
)

HUNAN_PROJECT_DECLARATION_PARSER_RULES = _project_parser_rules(
    list_item="#con_two_1 li",
    title=(
        "css:h1.article_title, h1.content_title, h1.article-title, "
        ".article-title h1, .content-title h1, h1"
    ),
    published_at=(
        "css:.article_attr, .article-info, .content_attr, "
        "#NewsArticlePubDay, .time"
    ),
    content=(
        "css:#zoomcon.article_content, #zoomcon, .article-content, "
        ".article_content, .TRS_Editor, .trs_editor_view"
    ),
    prefer_list_title=True,
)

CHANGSHA_PROJECT_DECLARATION_PARSER_RULES = _project_parser_rules(
    list_item=".list_ul li",
    title="css:.xly_title",
    published_at="css:#NewsArticlePubDay, .xly_list",
    content="css:.xly_contens, .trs_editor_view",
)

WECHAT_MANUAL_PARSER_RULES = json.dumps(
    {
        "collection_mode": "manual",
        "allowed_hosts": ["mp.weixin.qq.com"],
        "force_dynamic_fetch": True,
        "request_timeout_sec": 60,
        "title": "css:#activity-name, h1.rich_media_title",
        "published_at": "css:#publish_time",
        "content": "css:#js_content",
    },
    ensure_ascii=False,
)

COMPETITOR_WECHAT_MANUAL_PARSER_RULES = json.dumps(
    {
        **json.loads(WECHAT_MANUAL_PARSER_RULES),
        "category": "竞品信息",
        "metadata": {
            "kind": "competitor_intelligence",
            "source": "WeChat",
            "topic": "人工公众号线索",
            "evidence_level": "公众号线索（待核验）",
        },
    },
    ensure_ascii=False,
)

INDUSTRY_MEETING_WECHAT_MANUAL_PARSER_RULES = json.dumps(
    {
        **json.loads(WECHAT_MANUAL_PARSER_RULES),
        "category": "行业会议",
        "metadata": {
            "kind": "industry_meeting",
            "source": "公众号/同行分享",
            "review_status": "待核验",
        },
    },
    ensure_ascii=False,
)

PUBMED_COMPETITOR_PARSER_RULES = json.dumps(
    {
        "crawl_mode": "pubmed",
        "max_results_per_topic": 25,
        "lookback_days": 730,
        "topics": [
            {
                "name": "脑胶质瘤",
                "query": (
                    "(glioma[Title/Abstract] OR glioblastoma[Title/Abstract]) AND "
                    '("drug therapy"[Title/Abstract] OR therapeutics[Title/Abstract] OR '
                    'treatment[Title/Abstract] OR inhibitor[Title/Abstract] OR '
                    'phase[Title/Abstract] OR "Clinical Trial"[Publication Type])'
                ),
            },
            {
                "name": "降尿酸药物",
                "query": (
                    "(hyperuricemia[Title/Abstract] OR gout[Title/Abstract]) AND "
                    '("urate-lowering"[Title/Abstract] OR uricosuric[Title/Abstract] OR '
                    '"xanthine oxidase inhibitor"[Title/Abstract] OR '
                    '"Clinical Trial"[Publication Type])'
                ),
            },
        ],
    },
    ensure_ascii=False,
)

CLINICAL_TRIALS_COMPETITOR_PARSER_RULES = json.dumps(
    {
        "crawl_mode": "clinical_trials",
        "max_results_per_topic": 25,
        "topics": [
            {
                "name": "脑胶质瘤",
                "condition_query": "Glioma OR Glioblastoma",
                "intervention_type": "DRUG",
            },
            {
                "name": "降尿酸药物",
                "condition_query": "Hyperuricemia OR Gout",
                "intervention_type": "DRUG",
            },
        ],
    },
    ensure_ascii=False,
)

MEETING_SOURCE_TEMPLATE_IDS = frozenset(
    {
        "dxy_pharmacy_meetings",
        "cpa_association",
        "bioon_meetings",
        "cphi_china_events",
        "wechat_industry_meetings",
    }
)

MEETING_ENABLED_TEMPLATE_IDS = frozenset(
    {
        "cpa_association",
        "bioon_meetings",
        "cphi_china_events",
    }
)

DXY_MEETING_PARSER_RULES = json.dumps(
    {
        "crawl_mode": "list_follow",
        "collection_mode": "stale",
        "disabled_reason": "官方药学会议列表当前最新展示内容停留在2024年，保留解析能力但不参与定时任务。",
        "list_item": ".x_ct1",
        "detail_link": ".x_title a@href",
        "same_host_only": True,
        "max_items": 20,
        "request_timeout_sec": 45,
        "title": "css:h1.title",
        "published_at": "css:.x_time",
        "content": "css:#j_article_desc .x_wrap1",
        "category": "行业会议",
        "metadata": {
            "kind": "industry_meeting",
            "source": "丁香会议",
        },
    },
    ensure_ascii=False,
)

CPA_MEETING_PARSER_RULES = json.dumps(
    {
        "crawl_mode": "list_follow",
        "list_item": "#clist li",
        "detail_link": ":scope a@href",
        "detail_include_keywords": ["do=info"],
        "detail_exclude_keywords": ["do=infolist", "page="],
        "same_host_only": True,
        "max_items": 30,
        "request_timeout_sec": 45,
        "title": "css:#clist > div:first-child",
        "published_at": "css:#ctis",
        "content": "css:#cpabody",
        "category": "行业会议",
        "metadata": {
            "kind": "industry_meeting",
            "source": "中国药学会",
        },
    },
    ensure_ascii=False,
)

BIOON_MEETING_PARSER_RULES = json.dumps(
    {
        "crawl_mode": "list_follow",
        "collection_mode": "intermittent",
        "constraint_note": "来源可能间歇返回腾讯验证码；系统只做正常重试，不绕过验证码或网站访问控制。",
        "list_item": ".meeting-list-item",
        "detail_link": "h2 a@href",
        "same_host_only": False,
        "max_items": 20,
        "request_timeout_sec": 25,
        "detail_retries": 0,
        "detail_retry_policy": "transient",
        "anti_bot_retry_on_block": True,
        "anti_bot_block_backoff_ms": 2000,
        "anti_bot_valid_selector": ".meeting-list-item, .banner-text h1",
        "title": "css:.banner-text h1",
        "content": "css:.banner-text",
        "category": "行业会议",
        "metadata": {
            "kind": "industry_meeting",
            "source": "生物谷",
        },
    },
    ensure_ascii=False,
)

CPHI_MEETING_PARSER_RULES = json.dumps(
    {
        "crawl_mode": "meeting_table",
        "meeting_year": 2026,
        "organizer": "CPHI & PMEC China",
        "registration_url": "https://reg.cphi-china.cn/",
        "request_timeout_sec": 45,
        "category": "行业会议",
        "metadata": {
            "kind": "industry_meeting",
            "source": "CPHI China",
        },
    },
    ensure_ascii=False,
)

NEW_DRUG_SOURCE_TEMPLATES = [
    {
        "id": "most_project_declaration",
        "label": "科技部项目通知与公示",
        "name": "科技部项目申报与结果公示采集",
        "start_url": "https://service.most.gov.cn/kjjh_tztg/",
        "cron_expr": "0 8,14 * * *",
        "parser_rules": MOST_PROJECT_DECLARATION_PARSER_RULES,
        "enabled": True,
        "description": "来自《新药部AI需求》：项目申报通知、项目申报结果公示。",
        "tags": ["申报通知", "结果公示", "政府网站", "科技部"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "guangdong_stc_notices",
        "label": "广东省科技厅通知公告",
        "name": "广东省科技厅项目申报与结果公示采集",
        "start_url": "https://gdstc.gd.gov.cn/zwgk_n/tzgg/index.html",
        "cron_expr": "5 8,14 * * *",
        "parser_rules": GUANGDONG_PROJECT_DECLARATION_PARSER_RULES,
        "enabled": True,
        "description": "来自《新药部AI需求》：采集广东省科技厅项目申报通知与结果公示。",
        "tags": ["申报通知", "结果公示", "政府网站", "广东"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "guangzhou_sti_notices",
        "label": "广州市科技局信息公开",
        "name": "广州市科技局项目申报与结果公示采集",
        "start_url": "https://kjj.gz.gov.cn/xxgk/kjglhxmjf/",
        "cron_expr": "10 8,14 * * *",
        "parser_rules": GUANGZHOU_PROJECT_DECLARATION_PARSER_RULES,
        "enabled": True,
        "description": "来自《新药部AI需求》：采集广州市科技局项目申报通知与结果公示。",
        "tags": ["申报通知", "结果公示", "政府网站", "广州"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "huangpu_sti_notices",
        "label": "黄埔区科技局通知公告",
        "name": "黄埔区科技局项目申报与结果公示采集",
        "start_url": "https://www.hp.gov.cn/gzjg/qzfgwhgzbm/qkxjsj/tzgg/index.html",
        "cron_expr": "15 8,14 * * *",
        "parser_rules": HUANGPU_PROJECT_DECLARATION_PARSER_RULES,
        "enabled": True,
        "description": "来自《新药部AI需求》：采集黄埔区科技局项目申报通知与结果公示。",
        "tags": ["申报通知", "结果公示", "政府网站", "黄埔"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "hengqin_announcements",
        "label": "横琴通知公告",
        "name": "横琴项目申报与结果公示采集",
        "start_url": "https://www.hengqin.gov.cn/macao_zh_hans/zwgk/tzgg/gg/?page=1",
        "cron_expr": "20 8,14 * * *",
        "parser_rules": HENGQIN_PROJECT_DECLARATION_PARSER_RULES,
        "enabled": True,
        "description": "来自《新药部AI需求》：采集横琴项目申报通知与结果公示。",
        "tags": ["申报通知", "结果公示", "政府网站", "横琴"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "hunan_stc_notices",
        "label": "湖南省科技厅通知公告",
        "name": "湖南省科技厅项目申报与结果公示采集",
        "start_url": "http://kjt.hunan.gov.cn/kjt/xxgk/tzgg/index.html",
        "cron_expr": "25 8,14 * * *",
        "parser_rules": HUNAN_PROJECT_DECLARATION_PARSER_RULES,
        "enabled": True,
        "description": "来自《新药部AI需求》：采集湖南省科技厅项目申报通知与结果公示。",
        "tags": ["申报通知", "结果公示", "政府网站", "湖南"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "changsha_sti_notices",
        "label": "长沙市科技局通知公告",
        "name": "长沙市科技局项目申报与结果公示采集",
        "start_url": "http://kjj.changsha.gov.cn/zfxxgk/tzgg_27202/",
        "cron_expr": "30 8,14 * * *",
        "parser_rules": CHANGSHA_PROJECT_DECLARATION_PARSER_RULES,
        "enabled": True,
        "description": "来自《新药部AI需求》：采集长沙市科技局项目申报通知与结果公示。",
        "tags": ["申报通知", "结果公示", "政府网站", "长沙"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "wechat_k_innovation",
        "label": "K创联盟公众号线索",
        "name": "K创联盟公众号线索登记",
        "start_url": "https://mp.weixin.qq.com/",
        "cron_expr": "0 9 * * *",
        "parser_rules": WECHAT_MANUAL_PARSER_RULES,
        "enabled": False,
        "description": "来自《新药部AI需求》：公众号来源，需人工登记文章链接或后续接入授权采集。",
        "tags": ["申报通知", "结果公示", "公众号", "线索"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "wechat_hengqin_biomed",
        "label": "横琴大健康生物医药产业协会公众号线索",
        "name": "横琴大健康生物医药产业协会公众号线索登记",
        "start_url": "https://mp.weixin.qq.com/",
        "cron_expr": "0 9 * * *",
        "parser_rules": WECHAT_MANUAL_PARSER_RULES,
        "enabled": False,
        "description": "来自《新药部AI需求》：公众号来源，需人工登记文章链接或后续接入授权采集。",
        "tags": ["申报通知", "结果公示", "公众号", "横琴", "线索"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "wechat_competitor_intelligence",
        "label": "竞品研发公众号线索",
        "name": "竞品研发公众号线索登记",
        "start_url": "https://mp.weixin.qq.com/",
        "cron_expr": "0 10 * * *",
        "parser_rules": COMPETITOR_WECHAT_MANUAL_PARSER_RULES,
        "enabled": False,
        "description": "需求3公众号来源：人工登记脑胶质瘤、降尿酸药物研发相关文章链接，不绕过平台限制。",
        "tags": ["竞品信息", "公众号", "脑胶质瘤", "降尿酸药物", "线索"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "wechat_industry_meetings",
        "label": "行业会议公众号/同行线索",
        "name": "行业会议公众号与同行分享登记",
        "start_url": "https://mp.weixin.qq.com/",
        "cron_expr": "0 9 * * *",
        "parser_rules": INDUSTRY_MEETING_WECHAT_MANUAL_PARSER_RULES,
        "enabled": False,
        "description": (
            "需求2人工来源：登记公众号或同行分享的行业会议文章链接，"
            "保留原始证据并在核验后进入会议列表。"
        ),
        "tags": ["行业会议", "公众号", "同行分享", "人工核验"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "dxy_pharmacy_meetings",
        "label": "丁香会议药学会议",
        "name": "丁香会议药学会议采集",
        "start_url": "https://meeting.dxy.cn/tag/list/category/pharmacy",
        "cron_expr": "35 9,15 * * *",
        "parser_rules": DXY_MEETING_PARSER_RULES,
        "enabled": False,
        "description": "需求2来源：页面可解析，但官方药学列表当前最新内容停留在2024年，默认停用以免把过期会议当成最新信息。",
        "tags": ["行业会议", "丁香会议", "药学"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "cpa_association",
        "label": "中国药学会",
        "name": "中国药学会会议资讯采集",
        "start_url": "https://www.cpa.org.cn/?classid=270&do=infolist",
        "cron_expr": "40 9,15 * * *",
        "parser_rules": CPA_MEETING_PARSER_RULES,
        "enabled": True,
        "description": "需求2自动采集：中国药学会会议列表及详情，提取时间、地点、主办方和报名入口。",
        "tags": ["行业会议", "协会", "药学会"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "bioon_meetings",
        "label": "生物谷会议",
        "name": "生物谷会议采集",
        "start_url": "https://www.bioon.com/meeting/newest",
        "cron_expr": "45 9,15 * * *",
        "parser_rules": BIOON_MEETING_PARSER_RULES,
        "enabled": True,
        "description": "需求2受限自动采集：已接入会议列表与详情；来源可能间歇返回腾讯验证码，系统只正常重试，不绕过访问控制。",
        "tags": ["行业会议", "生物谷", "生物医药"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "cphi_china_events",
        "label": "CPHI China",
        "name": "CPHI China 行业会议采集",
        "start_url": "https://www.cphi-china.cn/newconferences/list/",
        "cron_expr": "50 9,15 * * *",
        "parser_rules": CPHI_MEETING_PARSER_RULES,
        "enabled": True,
        "description": "需求2自动采集：把官方会议活动日程表拆分为可筛选的单条会议记录。",
        "tags": ["行业会议", "CPHI", "生物医药"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "pharnexcloud_drug_database",
        "label": "摩熵医药数据库（原药融云）",
        "name": "竞品研发数据库入口",
        "start_url": "https://vip.pharnexcloud.com/database/research",
        "cron_expr": "0 10 * * *",
        "parser_rules": None,
        "enabled": False,
        "description": "来自《新药部AI需求》：脑胶质瘤、降尿酸药物研发进展；数据库类来源涉及账号授权，默认仅登记入口。",
        "tags": ["竞品信息", "药融云", "摩熵医药", "数据库"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "pubmed_literature",
        "label": "PubMed 文献",
        "name": "PubMed 竞品文献入口",
        "start_url": "https://pubmed.ncbi.nlm.nih.gov/",
        "cron_expr": "0 10 * * *",
        "parser_rules": PUBMED_COMPETITOR_PARSER_RULES,
        "enabled": True,
        "description": "需求3自动采集：通过NCBI官方接口监测脑胶质瘤、降尿酸药物研发文献。",
        "tags": ["竞品信息", "PubMed", "文献", "脑胶质瘤", "降尿酸药物"],
        "usage_count": 0,
        "last_used_at": None,
    },
    {
        "id": "clinical_trials_competitor",
        "label": "ClinicalTrials.gov 临床试验",
        "name": "ClinicalTrials.gov 竞品临床试验采集",
        "start_url": "https://clinicaltrials.gov/search",
        "cron_expr": "15 10 * * *",
        "parser_rules": CLINICAL_TRIALS_COMPETITOR_PARSER_RULES,
        "enabled": True,
        "description": (
            "需求3自动采集：通过ClinicalTrials.gov官方API监测脑胶质瘤、"
            "降尿酸药物临床试验的阶段、状态、申办方和试验编号。"
        ),
        "tags": [
            "竞品信息",
            "ClinicalTrials.gov",
            "临床试验",
            "脑胶质瘤",
            "降尿酸药物",
        ],
        "usage_count": 0,
        "last_used_at": None,
    },
]

DEFAULT_TEMPLATES = [*DEFAULT_TEMPLATES, *NEW_DRUG_SOURCE_TEMPLATES]


class TemplateService:
    def __init__(
        self,
        template_repo: TemplateRepository,
        template_file: Path | None = None,
    ) -> None:
        self.template_repo = template_repo
        server_dir = Path(__file__).resolve().parents[2]
        self._using_default_template_file = template_file is None
        self.template_file = template_file or server_dir / "storage" / "templates" / "task_templates.json"

    async def ensure_seed_data(
        self,
        *,
        sync_required_sources: bool = False,
    ) -> None:
        seed_templates = self._load_seed_templates()
        missing_templates: list[TaskTemplateRead] = []
        required_source_ids = {str(item["id"]) for item in NEW_DRUG_SOURCE_TEMPLATES}
        for template in seed_templates:
            existing = await self.template_repo.get_by_id(template.id)
            if existing is None:
                missing_templates.append(template)
            elif sync_required_sources and template.id in required_source_ids:
                await self.template_repo.update(
                    existing,
                    TaskTemplateUpdate(**template.model_dump(exclude={"id", "usage_count", "last_used_at"})),
                )

        if missing_templates:
            await self.template_repo.create_many(missing_templates)

    async def sync_required_source_templates(self) -> None:
        """Explicitly restore required source templates to the shipped contracts."""
        await self.ensure_seed_data(sync_required_sources=True)

    async def list_task_templates(self) -> list[TaskTemplateRead]:
        templates = await self.template_repo.list_all()
        return [TaskTemplateRead.model_validate(item) for item in templates]

    async def create_task_template(self, payload: TaskTemplateCreate) -> TaskTemplateRead:
        template_id = payload.id or self._slugify(payload.label)
        if await self.template_repo.get_by_id(template_id) is not None:
            raise ValueError(f"Template {template_id} already exists")

        template = await self.template_repo.create(
            TaskTemplateRead(
                id=template_id,
                **payload.model_dump(exclude={"id"}),
            )
        )
        return TaskTemplateRead.model_validate(template)

    async def update_task_template(
        self,
        template_id: str,
        payload: TaskTemplateUpdate,
    ) -> TaskTemplateRead:
        template = await self.template_repo.get_by_id(template_id)
        if template is None:
            raise LookupError(f"Template {template_id} not found")

        updated = await self.template_repo.update(template, payload)
        return TaskTemplateRead.model_validate(updated)

    async def delete_task_template(self, template_id: str) -> None:
        template = await self.template_repo.get_by_id(template_id)
        if template is None:
            raise LookupError(f"Template {template_id} not found")
        await self.template_repo.delete(template)

    async def track_task_template_use(self, template_id: str) -> TaskTemplateRead:
        template = await self.template_repo.get_by_id(template_id)
        if template is None:
            raise LookupError(f"Template {template_id} not found")

        tracked = await self.template_repo.track_use(template, datetime.now(UTC))
        return TaskTemplateRead.model_validate(tracked)

    def _load_seed_templates(self) -> list[TaskTemplateRead]:
        if self.template_file.exists():
            loaded = json.loads(self.template_file.read_text(encoding="utf-8"))
            if not isinstance(loaded, list):
                raise ValueError("Template storage must contain a list")
            seed_items = loaded
            if self._using_default_template_file:
                loaded_ids = {str(item.get("id")) for item in loaded if isinstance(item, dict)}
                seed_items = [
                    *loaded,
                    *[item for item in NEW_DRUG_SOURCE_TEMPLATES if item["id"] not in loaded_ids],
                ]
        else:
            seed_items = DEFAULT_TEMPLATES

        templates: list[TaskTemplateRead] = []
        for item in seed_items:
            normalized = dict(item)
            normalized.setdefault("usage_count", 0)
            normalized.setdefault("last_used_at", None)
            normalized.setdefault("tags", [])
            templates.append(TaskTemplateRead.model_validate(normalized))
        return templates

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
        return slug or "template"
