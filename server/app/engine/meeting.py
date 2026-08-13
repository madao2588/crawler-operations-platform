from __future__ import annotations

import hashlib
import html as html_module
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup, Tag


_MEETING_TITLE_MARKERS = (
    "会议",
    "大会",
    "年会",
    "论坛",
    "峰会",
    "研讨会",
    "展会",
    "活动",
)
_MEETING_ACTION_MARKERS = ("举办", "召开", "举行")
_TRAILING_PUNCTUATION = " \t\r\n。；;，,"
_REGISTRATION_TEXT_MARKERS = ("报名", "注册", "参会", "购票", "预订", "立即参加")
_OFFICIAL_TEXT_MARKERS = ("官网", "官方网站", "会议网址", "大会网址", "官方入口")
_LOGIN_URL_MARKERS = (
    "/auth/login",
    "/login",
    "/signin",
    "sign-in",
    "/sso",
    "/oauth",
    "/passport",
)
_DETAIL_PATH_MARKERS = (
    "/detail",
    "/article",
    "/news",
    "/content",
    "/show",
    "/view",
    "/info",
)
_STRONG_REGISTRATION_URL_PATTERN = re.compile(
    r"(^|[./_-])(register|registration|signup|sign-up|enroll|booking|apply|attend|ticket|reg)([./_-]|$)"
)


@dataclass(frozen=True)
class MeetingRecord:
    title: str
    meeting_date: str
    location: str
    organizer: str
    registration_url: str
    source_url: str
    industry: str = ""
    registration_deadline: str = ""

    @property
    def metadata(self) -> dict[str, str]:
        values = {
            "kind": "industry_meeting",
            "meeting_date": self.meeting_date,
            "location": self.location,
            "organizer": self.organizer,
            "registration_url": self.registration_url,
            "registration_deadline": self.registration_deadline,
            "industry": self.industry,
        }
        return {key: value for key, value in values.items() if value}

    @property
    def content_html(self) -> str:
        rows = [
            ("会议时间", self.meeting_date),
            ("会议地点", self.location),
            ("主办方", self.organizer),
            ("所属行业", self.industry),
            ("报名截止", self.registration_deadline),
        ]
        table_rows = "".join(
            f"<tr><th>{html_module.escape(label)}</th>"
            f"<td>{html_module.escape(value)}</td></tr>"
            for label, value in rows
            if value
        )
        registration = (
            '<p><a href="'
            f'{html_module.escape(self.registration_url, quote=True)}'
            '">会议报名 / 官方入口</a></p>'
            if self.registration_url
            else ""
        )
        return (
            "<article>"
            f"<h1>{html_module.escape(self.title)}</h1>"
            f"<table>{table_rows}</table>"
            f"{registration}"
            "</article>"
        )

    @property
    def content_text(self) -> str:
        values = [
            self.title,
            f"会议时间：{self.meeting_date}" if self.meeting_date else "",
            f"会议地点：{self.location}" if self.location else "",
            f"主办方：{self.organizer}" if self.organizer else "",
            f"所属行业：{self.industry}" if self.industry else "",
            (
                f"报名截止：{self.registration_deadline}"
                if self.registration_deadline
                else ""
            ),
        ]
        return "\n".join(value for value in values if value)


def extract_meeting_metadata(
    html: str,
    *,
    source_url: str,
) -> dict[str, str]:
    """Extract stable, reader-facing meeting fields from a detail page."""
    soup = BeautifulSoup(html, "html.parser")
    lines = _text_lines(soup)
    metadata: dict[str, str] = {"kind": "industry_meeting"}

    meeting_date = _labeled_value(
        lines,
        ("会议时间", "大会时间", "活动时间", "召开时间"),
    )
    if not meeting_date:
        meeting_date = _section_value(lines, ("时间",))
    location = _labeled_value(
        lines,
        ("会议地点", "大会地点", "活动地点", "召开地点"),
    )
    if not location:
        location = _section_value(lines, ("地点",))
    organizer = _labeled_value(lines, ("主办方", "主办单位", "主办机构"))
    if not organizer:
        organizer = _organizer_from_sentence(lines)
    deadline = _labeled_value(
        lines,
        ("报名截止时间", "报名截止日期", "报名截止", "注册截止时间", "注册截止日期", "注册截止"),
    )
    registration_url = _registration_url(soup, source_url)

    for key, value in (
        ("meeting_date", meeting_date),
        ("location", location),
        ("organizer", organizer),
        ("registration_deadline", deadline),
        ("registration_url", registration_url),
    ):
        if value:
            metadata[key] = value
    return metadata


def is_valid_meeting_record(title: str | None, metadata: dict[str, str]) -> bool:
    normalized_title = (title or "").strip()
    has_core_field = bool(
        metadata.get("meeting_date")
        or metadata.get("location")
        or metadata.get("start_date")
    )
    has_meeting_title = any(marker in normalized_title for marker in _MEETING_TITLE_MARKERS)
    has_hosting_title = has_core_field and any(
        marker in normalized_title for marker in _MEETING_ACTION_MARKERS
    )
    return (has_meeting_title or has_hosting_title) and has_core_field


def extract_meeting_table_records(
    html: str,
    *,
    source_url: str,
    rules: dict[str, object],
) -> list[MeetingRecord]:
    """Turn the CPHI conference schedule table into individual meeting rows."""
    soup = BeautifulSoup(html, "html.parser")
    table = next(
        (
            candidate
            for candidate in soup.select("table")
            if "会议活动名称" in candidate.get_text(" ", strip=True)
        ),
        None,
    )
    if table is None:
        return []

    headers = [
        cell.get_text(" ", strip=True)
        for cell in table.select("thead th, thead td")
    ]
    date_headers = [value for value in headers if re.fullmatch(r"\d{1,2}/\d{1,2}", value)]
    if not date_headers:
        first_row = table.find("tr")
        if first_row is not None:
            date_headers = [
                value
                for value in (
                    cell.get_text(" ", strip=True)
                    for cell in first_row.find_all(["th", "td"], recursive=False)
                )
                if re.fullmatch(r"\d{1,2}/\d{1,2}", value)
            ]
    if not date_headers:
        return []

    year = _bounded_year(rules.get("meeting_year"))
    organizer = str(rules.get("organizer") or "").strip()
    registration_url = str(rules.get("registration_url") or "").strip()
    current_industry = ""
    records: list[MeetingRecord] = []

    body_rows = table.select("tbody tr") or table.select("tr")[1:]
    for row in body_rows:
        cells = row.find_all(["th", "td"], recursive=False)
        if not cells:
            continue
        title_index = _cell_index_by_width(cells, "514")
        location_index = _cell_index_by_width(cells, "167")
        if title_index is None:
            title_index = _guess_title_index(cells)
        if title_index is None:
            continue

        if title_index > 0:
            candidate_industry = cells[title_index - 1].get_text(" ", strip=True)
            if candidate_industry:
                current_industry = candidate_industry
        title = cells[title_index].get_text(" ", strip=True)
        if not title or title == "会议活动名称":
            continue

        date_cells = cells[title_index + 1 : title_index + 1 + len(date_headers)]
        active_dates = [
            _iso_date(year, header)
            for header, cell in zip(date_headers, date_cells, strict=False)
            if cell.get_text(" ", strip=True)
        ]
        location = (
            cells[location_index].get_text(" ", strip=True)
            if location_index is not None
            else ""
        )
        meeting_date = "、".join(active_dates)
        if not meeting_date:
            continue

        fingerprint = hashlib.sha256(
            f"{title}\n{meeting_date}\n{location}".encode()
        ).hexdigest()[:16]
        record = MeetingRecord(
            title=title,
            meeting_date=meeting_date,
            location=location,
            organizer=organizer,
            registration_url=registration_url,
            source_url=f"{source_url.rstrip('#')}#meeting-{fingerprint}",
            industry=current_industry,
        )
        if is_valid_meeting_record(record.title, record.metadata):
            records.append(record)
    return records


def _text_lines(soup: BeautifulSoup) -> list[str]:
    values = []
    for raw in soup.get_text("\n", strip=True).splitlines():
        value = re.sub(r"\s+", " ", raw).strip()
        if value:
            values.append(value)
    return values


def _clean_value(value: str) -> str:
    return value.strip(_TRAILING_PUNCTUATION)


def _labeled_value(lines: list[str], labels: tuple[str, ...]) -> str:
    pattern = "|".join(re.escape(label) for label in labels)
    for line in lines:
        match = re.match(
            rf"^(?:[（(]?[一二三四五六七八九十\d]+[、.)）]\s*)?"
            rf"(?:{pattern})\s*[：:]\s*(.+)$",
            line,
        )
        if match:
            value = _clean_value(match.group(1))
            if value:
                return value
    return ""


def _section_value(lines: list[str], labels: tuple[str, ...]) -> str:
    pattern = "|".join(re.escape(label) for label in labels)
    for line in lines:
        match = re.match(
            rf"^(?:[（(]?[一二三四五六七八九十\d]+[、.)）]\s*)?"
            rf"(?:{pattern})\s*[：:]\s*(.+)$",
            line,
        )
        if match:
            value = _clean_value(match.group(1))
            if value:
                return value
    return ""


def _organizer_from_sentence(lines: list[str]) -> str:
    for line in lines:
        match = re.search(r"由(.{2,100}?)(?:共同)?主办", line)
        if match:
            return _clean_value(match.group(1).strip("“”\""))
    return ""


def _registration_url(soup: BeautifulSoup, source_url: str) -> str:
    scored: list[tuple[int, str]] = []
    for anchor in soup.select("a[href]"):
        href = str(anchor.get("href") or "").strip()
        if not href or href.startswith(("javascript:", "mailto:", "#")):
            continue
        text = anchor.get_text(" ", strip=True)
        parent_text = anchor.parent.get_text(" ", strip=True) if isinstance(anchor.parent, Tag) else text
        combined = f"{parent_text} {text}"
        resolved = urljoin(source_url, href)
        score = 0
        if any(marker in combined for marker in _REGISTRATION_TEXT_MARKERS):
            score += 4
        if any(marker in combined for marker in _OFFICIAL_TEXT_MARKERS):
            score += 2
        if score and is_valid_registration_url(
            resolved,
            source_url=source_url,
            context_text=combined,
        ):
            scored.append((score, resolved))
    if not scored:
        return ""
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def is_valid_registration_url(
    url: str | None,
    *,
    source_url: str = "",
    context_text: str = "",
) -> bool:
    candidate = (url or "").strip()
    if not candidate:
        return False

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False

    normalized_url = candidate.lower()
    path = (parsed.path or "").lower()
    query = {key.lower(): values for key, values in parse_qs(parsed.query).items()}
    normalized_text = context_text.lower()

    if any(marker in normalized_url for marker in _LOGIN_URL_MARKERS):
        return False

    has_strong_url_marker = bool(
        _STRONG_REGISTRATION_URL_PATTERN.search(parsed.netloc.lower())
        or _STRONG_REGISTRATION_URL_PATTERN.search(path)
    )
    has_registration_text = any(marker in normalized_text for marker in _REGISTRATION_TEXT_MARKERS)
    has_official_text = any(marker in normalized_text for marker in _OFFICIAL_TEXT_MARKERS)

    looks_like_detail_page = any(marker in path for marker in _DETAIL_PATH_MARKERS) or (
        query.get("do", [""])[0].lower() in {"info", "show", "view", "detail"}
    ) or any(key in query for key in ("id", "cid", "articleid", "contentid"))
    if looks_like_detail_page and not has_strong_url_marker:
        return False

    if has_strong_url_marker:
        return True

    if has_registration_text:
        return not looks_like_detail_page

    if has_official_text:
        source_host = urlparse(source_url).netloc.lower()
        return parsed.netloc.lower() != source_host and not looks_like_detail_page

    return False


def _cell_index_by_width(cells: list[Tag], width: str) -> int | None:
    for index, cell in enumerate(cells):
        if str(cell.get("width") or "").strip() == width:
            return index
    return None


def _guess_title_index(cells: list[Tag]) -> int | None:
    for index, cell in enumerate(cells):
        value = cell.get_text(" ", strip=True)
        if any(marker in value for marker in _MEETING_TITLE_MARKERS):
            return index
    return None


def _bounded_year(value: object) -> int:
    try:
        year = int(value)
    except (TypeError, ValueError):
        year = 2026
    return max(2000, min(year, 2100))


def _iso_date(year: int, month_day: str) -> str:
    month, day = (int(part) for part in month_day.split("/", maxsplit=1))
    return f"{year:04d}-{month:02d}-{day:02d}"
