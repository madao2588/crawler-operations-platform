from collections import Counter
from urllib.parse import urlparse


DEFAULT_NOTICE_KEYWORDS = (
    "项目申报",
    "申报通知",
    "申报结果",
    "公示",
    "截止时间",
    "生物医药",
    "医药",
    "药学",
    "会议",
    "论坛",
    "CPHI",
    "脑胶质瘤",
    "降尿酸",
    "适应症",
    "研发阶段",
    "临床",
    "竞品",
    "招标",
    "采购",
    "中标",
    "原料药",
    "制剂",
    "注射液",
    "药品",
    "集采",
    "医院",
)

HIGH_PRIORITY_KEYWORDS = (
    "项目申报",
    "申报通知",
    "申报结果",
    "截止时间",
    "脑胶质瘤",
    "降尿酸",
    "临床",
    "竞品",
)

PROJECT_DECLARATION_SIGNAL_KEYWORDS = (
    "申报",
    "组织申报",
    "申报通知",
    "申报指南",
    "征集",
    "受理",
    "截止时间",
    "入库储备",
    "揭榜挂帅",
    "项目榜单",
)

PROJECT_RESULT_SIGNAL_KEYWORDS = (
    "结果公示",
    "申报结果",
    "立项公示",
    "拟立项",
    "拟支持",
    "拟资助",
    "拟补助",
    "拟奖励",
    "拟入库",
    "验收结果",
    "验收结论",
    "评审结果",
    "审核结果",
    "认定结果",
    "遴选结果",
    "评估结果",
    "立项名单",
    "支持经费公示",
    "资助经费公示",
    "补助经费公示",
    "视同立项",
    "拟登记",
    "名单公示",
    "名单的公示",
)

PROJECT_PROCESS_SIGNAL_KEYWORDS = (
    "验收工作",
    "评审答辩",
    "答辩通知",
    "项目变更",
)

PROJECT_RESULT_SIGNAL_KEYWORD_GROUPS = (
    ("入库", "名单"),
    ("资助", "名单"),
    ("补助", "名单"),
    ("支持", "名单"),
    ("奖励", "名单"),
    ("项目", "名单", "公布"),
    ("项目", "名单", "公示"),
)

PROJECT_RESULT_IRRELEVANCE_KEYWORDS = (
    "作品征集",
    "获奖名单",
    "更名高新技术企业",
    "异地搬迁高新技术企业",
    "创新药品医疗器械目录",
)

PROJECT_NOTICE_RELEVANCE_CONTEXT_KEYWORDS = (
    "项目",
    "申报",
    "指南",
    "征集",
    "评审",
    "立项",
    "拟支持",
    "补助",
    "资助",
    "奖励",
    "经费",
    "验收",
    "认定",
    "入库",
    "揭榜挂帅",
    "科技计划",
    "科研",
    "研发",
    "课题",
    "专项",
    "基金",
    "资金",
    "创新",
    "成果转化",
    "政策兑现",
    "技术攻关",
    "企业",
)

PROJECT_NOTICE_IRRELEVANCE_KEYWORDS = (
    "登录",
    "注册",
    "邮箱",
    "微博",
    "微信",
    "english",
    "招生",
    "录取",
    "入学",
    "学位",
    "幼儿园",
    "中小学",
    "小学",
    "中学",
    "学校",
    "学生",
    "教师",
    "教育",
    "招聘",
    "招考",
    "考试",
    "面试",
    "公务员",
    "事业单位",
    "职称",
    "征兵",
    "住房",
    "不动产",
    "土地出让",
    "采购公告",
    "招标公告",
    "中标公告",
    "工程建设",
    "指南意见",
)

PROJECT_NOTICE_CATEGORIES = ("项目申报",)
NON_PROJECT_NOTICE_CATEGORIES = ("行业会议", "竞品信息")
PROJECT_NOTICE_METADATA_KINDS = ("project_notice", "project_declaration", "project_result")
NON_PROJECT_NOTICE_METADATA_KINDS = ("industry_meeting", "competitor_intelligence")
PROJECT_NOTICE_TASK_KEYWORDS = (
    "项目申报",
    "项目申请",
    "科技计划项目",
    "项目线索",
)


CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "项目申报": (
        "项目申报",
        "申报通知",
        "申报结果",
        "公示",
        "科技厅",
        "科技局",
        "截止时间",
    ),
    "行业会议": (
        "会议",
        "论坛",
        "大会",
        "报名",
        "CPHI",
        "药学会",
        "生物谷",
    ),
    "竞品信息": (
        "竞品",
        "研发进展",
        "脑胶质瘤",
        "降尿酸",
        "适应症",
        "研发阶段",
        "临床",
        "药物名称",
        "PubMed",
    ),
}

# Keep legacy values readable while accepting every status exposed by the
# current review UI.  Existing rows may still contain "有效"/"无效".
REVIEW_STATUSES = ("待关注", "重点关注", "已跟进", "已忽略", "有效", "无效")


def effective_active_keywords(active_from_rules: list[str]) -> list[str]:
    """Return enabled database rules, deduplicated case-insensitively."""
    return _merge_keywords(active_from_rules, [])


def effective_high_priority_keywords(high_priority_from_rules: list[str]) -> list[str]:
    """Return high-priority database rules; content quality is independent."""
    return _merge_keywords(high_priority_from_rules, [])


def _merge_keywords(primary: list[str], defaults: list[str]) -> list[str]:
    merged = list(primary) + defaults
    seen: set[str] = set()
    out: list[str] = []
    for raw in merged:
        word = (raw or "").strip()
        if not word:
            continue
        key = word.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(word)
    return out


def extract_source_site(url: str) -> str:
    hostname = urlparse(url).hostname or ""
    return hostname.removeprefix("www.") or "unknown"


def extract_matched_keywords(parts: list[str | None], active_keywords: list[str]) -> list[str]:
    text = " ".join(part for part in parts if part).lower()
    return [keyword for keyword in active_keywords if keyword.lower() in text]


def is_high_priority_notice(*, matched_keywords: list[str], high_priority_keywords: list[str]) -> bool:
    return any(keyword in high_priority_keywords for keyword in matched_keywords)


def is_high_quality_notice(*, quality_score: int) -> bool:
    return quality_score >= 60


def build_notice_summary(content_text: str | None, max_length: int = 140) -> str:
    text = (content_text or "").strip()
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return f"{text[:max_length].rstrip()}..."


def classify_notice_category(parts: list[str | None]) -> str:
    text = " ".join(part for part in parts if part).lower()
    if not text:
        return "未分类"
    best_category = "未分类"
    best_score = 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword.lower() in text)
        if score > best_score:
            best_category = category
            best_score = score
    return best_category


def project_notice_has_project_context(
    *,
    category: str | None = None,
    metadata: dict[str, object] | None = None,
    task_name: str | None = None,
) -> bool:
    normalized_category = (category or "").strip()
    if normalized_category in NON_PROJECT_NOTICE_CATEGORIES:
        return False
    if normalized_category in PROJECT_NOTICE_CATEGORIES:
        return True

    metadata_kind = str((metadata or {}).get("kind") or "").strip().lower()
    if metadata_kind in NON_PROJECT_NOTICE_METADATA_KINDS:
        return False
    if metadata_kind in PROJECT_NOTICE_METADATA_KINDS:
        return True

    task_text = (task_name or "").strip().lower()
    return any(keyword.lower() in task_text for keyword in PROJECT_NOTICE_TASK_KEYWORDS)


def project_notice_kind(
    parts: list[str | None],
    *,
    category: str | None = None,
    metadata: dict[str, object] | None = None,
    task_name: str | None = None,
) -> str:
    has_context_hints = bool((category or "").strip() or (metadata or {}).get("kind") or (task_name or "").strip())
    if has_context_hints and not project_notice_has_project_context(
        category=category,
        metadata=metadata,
        task_name=task_name,
    ):
        return "其他项目线索"
    title = (parts[0] or "").lower() if parts else ""
    supporting_text = " ".join(part for part in parts[1:] if part).lower()
    if _has_project_result_irrelevance(title):
        return "其他项目线索"
    if _has_project_result_signal(title):
        return "结果公示"
    if _has_project_declaration_signal(title):
        return "申报通知"
    if _has_project_process_signal(title):
        return "其他项目线索"
    if _has_project_result_signal(supporting_text):
        return "结果公示"
    if _has_project_declaration_signal(supporting_text):
        return "申报通知"
    return "其他项目线索"


def _has_project_declaration_signal(text: str) -> bool:
    return any(keyword.lower() in text for keyword in PROJECT_DECLARATION_SIGNAL_KEYWORDS)


def _has_project_result_signal(text: str) -> bool:
    if _has_project_result_irrelevance(text):
        return False
    if any(keyword.lower() in text for keyword in PROJECT_RESULT_SIGNAL_KEYWORDS):
        return True
    return any(
        all(keyword.lower() in text for keyword in keyword_group)
        for keyword_group in PROJECT_RESULT_SIGNAL_KEYWORD_GROUPS
    )


def _has_project_result_irrelevance(text: str) -> bool:
    return any(keyword.lower() in text for keyword in PROJECT_RESULT_IRRELEVANCE_KEYWORDS)


def _has_project_process_signal(text: str) -> bool:
    return any(keyword.lower() in text for keyword in PROJECT_PROCESS_SIGNAL_KEYWORDS)


def normalize_review_status(value: str | None) -> str:
    status = (value or "待关注").strip()
    if status not in REVIEW_STATUSES:
        raise ValueError(f"review_status must be one of {', '.join(REVIEW_STATUSES)}")
    return status


def keyword_heat_from_texts(texts: list[str], active_keywords: list[str]) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for text in texts:
        matched = extract_matched_keywords([text], active_keywords)
        counter.update(matched)
    return counter.most_common(10)
