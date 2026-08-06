from __future__ import annotations

import asyncio
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

import httpx


EUTILS_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_ARTICLE_BASE_URL = "https://pubmed.ncbi.nlm.nih.gov"

CLINICAL_STAGE_UNCLEAR = "临床试验（阶段未明确）"
PRECLINICAL_STAGE = "临床前研究"
UNKNOWN_STAGE = "研究阶段未明确"

EVIDENCE_SYNTHESIS = "证据综合"
CLINICAL_EVIDENCE = "临床试验证据"
REVIEW_EVIDENCE = "综述证据"
PRECLINICAL_EVIDENCE = "临床前证据"
EXPLORATORY_EVIDENCE = "探索性研究证据"

PHASE_LABELS = {
    "iv": "\u4e34\u5e8a\u2163\u671f",
    "4": "\u4e34\u5e8a\u2163\u671f",
    "iii": "\u4e34\u5e8a\u2162\u671f",
    "3": "\u4e34\u5e8a\u2162\u671f",
    "ii": "\u4e34\u5e8a\u2161\u671f",
    "2": "\u4e34\u5e8a\u2161\u671f",
    "i": "\u4e34\u5e8a\u2160\u671f",
    "1": "\u4e34\u5e8a\u2160\u671f",
}
PHASE_ORDER = ("iv", "4", "iii", "3", "ii", "2", "i", "1")

CLINICAL_MARKERS = (
    "clinical trial",
    "clinical study",
    "randomized controlled trial",
    "randomized study",
    "open-label",
    "double-blind",
    "dose-escalation",
    "dose expansion",
)
PRECLINICAL_MARKERS = (
    "preclinical",
    "in vitro",
    "in vivo",
    "animal study",
    "animal model",
    "xenograft",
    "mouse model",
    "mouse models",
    "murine model",
    "murine models",
    "cell line",
    "cell lines",
)
TRIAL_STATUS_MARKERS = (
    "active, not recruiting",
    "not yet recruiting",
    "enrolling by invitation",
    "recruiting",
    "completed",
    "terminated",
    "withdrawn",
    "suspended",
)
COUNTRY_PATTERNS = (
    ("United States", re.compile(r"\b(?:United States|USA|U\.S\.A\.|U\.S\.)\b", re.IGNORECASE)),
    ("Canada", re.compile(r"\bCanada\b", re.IGNORECASE)),
    ("China", re.compile(r"\bChina\b", re.IGNORECASE)),
    ("Japan", re.compile(r"\bJapan\b", re.IGNORECASE)),
    ("South Korea", re.compile(r"\b(?:South Korea|Republic of Korea)\b", re.IGNORECASE)),
    ("United Kingdom", re.compile(r"\b(?:United Kingdom|UK)\b", re.IGNORECASE)),
    ("Germany", re.compile(r"\bGermany\b", re.IGNORECASE)),
    ("France", re.compile(r"\bFrance\b", re.IGNORECASE)),
    ("Italy", re.compile(r"\bItaly\b", re.IGNORECASE)),
    ("Spain", re.compile(r"\bSpain\b", re.IGNORECASE)),
    ("Australia", re.compile(r"\bAustralia\b", re.IGNORECASE)),
    ("Israel", re.compile(r"\bIsrael\b", re.IGNORECASE)),
)
COMPANY_PATTERN = re.compile(
    r"\b([A-Z][A-Za-z0-9&.,' -]{1,80}?"
    r"(?:Therapeutics|Pharmaceuticals?|Pharma|Biotech|Biosciences|Bio|"
    r"Laboratories|Labs|Inc\.?|Ltd\.?|LLC|PLC|Corp\.?|Corporation|Company|Co\.|GmbH|S\.A\.))\b"
)
TRIAL_ID_PATTERNS = (
    re.compile(r"\bNCT\d{8}\b", re.IGNORECASE),
    re.compile(r"\b\d{4}-\d{6}-\d{2}\b"),
    re.compile(r"\bChiCTR[-A-Z0-9]+\b", re.IGNORECASE),
    re.compile(r"\bCTRI/\d{4}/\d{2}/\d{6}\b", re.IGNORECASE),
)
TARGET_PATTERN = re.compile(
    r"\b(?:HER2|PD-1|PD-L1|VEGF(?:R)?|FGFR\d?|ALK|ROS1|BRAF(?:\s*V600E)?|"
    r"KRAS(?:\s*G12C)?|IDH1|IDH2|CD19|CD20|BCMA|MET|c-MET|PI3K|mTOR|IL-23|IL23)\b",
    re.IGNORECASE,
)
ASSET_PATTERNS = (
    re.compile(r"\b[A-Z]{2,8}[-/][A-Z0-9]{1,10}\b"),
    re.compile(r"\b[A-Z]{2,}[0-9]{2,}[A-Z0-9-]*\b"),
    re.compile(
        r"\b[A-Z][a-z0-9]{2,}(?:mab|nib|parib|ciclib|tinib|cept|limab|zumab|fenib|sertib)\b",
        re.IGNORECASE,
    ),
)
ASSET_STOPWORDS = {
    "DNA",
    "RNA",
    "MRI",
    "PET",
    "USA",
    "RESULTS",
    "BACKGROUND",
    "PHASE",
}
ASSET_EXCLUDE_PATTERN = re.compile(r"^NCT\d{8}$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class DevelopmentStageAssessment:
    stage: str
    confidence: str
    evidence_snippet: str


@dataclass(frozen=True, slots=True)
class PubMedArticle:
    pmid: str
    topic: str
    title: str
    abstract: str
    journal: str | None
    published_at: datetime | None
    doi: str | None
    authors: list[str]
    organizations: list[str]
    drugs: list[str]
    keywords: list[str]
    publication_types: list[str]
    development_stage: str
    evidence_level: str
    mesh_terms: list[str]
    targets: list[str]
    sponsor_hints: list[str]
    trial_ids: list[str]
    trial_status: str | None
    countries: list[str]
    development_stage_evidence: str
    development_stage_confidence: str

    @property
    def source_url(self) -> str:
        return f"{PUBMED_ARTICLE_BASE_URL}/{self.pmid}/"


class PubMedClient:
    def __init__(
        self,
        *,
        http_client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 30.0,
        request_interval_seconds: float = 0.34,
    ) -> None:
        self._http_client = http_client
        self._timeout_seconds = timeout_seconds
        self._request_interval_seconds = max(0.0, request_interval_seconds)
        self._request_lock = asyncio.Lock()
        self._last_request_at = 0.0

    async def fetch_topic(
        self,
        *,
        topic: str,
        query: str,
        max_results: int,
        lookback_days: int,
    ) -> list[PubMedArticle]:
        if self._http_client is not None:
            return await self._fetch_topic_with_client(
                self._http_client,
                topic=topic,
                query=query,
                max_results=max_results,
                lookback_days=lookback_days,
            )

        headers = {
            "User-Agent": "crawler-system/1.0 (PubMed competitor intelligence monitor)",
        }
        async with httpx.AsyncClient(
            headers=headers,
            timeout=self._timeout_seconds,
            follow_redirects=True,
        ) as client:
            return await self._fetch_topic_with_client(
                client,
                topic=topic,
                query=query,
                max_results=max_results,
                lookback_days=lookback_days,
            )

    async def _fetch_topic_with_client(
        self,
        client: httpx.AsyncClient,
        *,
        topic: str,
        query: str,
        max_results: int,
        lookback_days: int,
    ) -> list[PubMedArticle]:
        retmax = max(1, min(int(max_results), 100))
        reldate = max(1, min(int(lookback_days), 3650))
        search_response = await self._get(
            client,
            f"{EUTILS_BASE_URL}/esearch.fcgi",
            params={
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retmax": retmax,
                "sort": "pub date",
                "datetype": "pdat",
                "reldate": reldate,
                "tool": "crawler_system",
            },
        )
        search_response.raise_for_status()
        payload = search_response.json()
        raw_ids = payload.get("esearchresult", {}).get("idlist", [])
        ids = [str(item).strip() for item in raw_ids if str(item).strip()]
        if not ids:
            return []

        fetch_response = await self._get(
            client,
            f"{EUTILS_BASE_URL}/efetch.fcgi",
            params={
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "xml",
                "tool": "crawler_system",
            },
        )
        fetch_response.raise_for_status()
        return parse_pubmed_xml(fetch_response.text, topic=topic)

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, object],
    ) -> httpx.Response:
        async with self._request_lock:
            elapsed = time.monotonic() - self._last_request_at
            remaining = self._request_interval_seconds - elapsed
            if self._last_request_at > 0 and remaining > 0:
                await asyncio.sleep(remaining)
            response = await client.get(url, params=params)
            self._last_request_at = time.monotonic()
            return response


def parse_pubmed_xml(xml_text: str, *, topic: str) -> list[PubMedArticle]:
    root = ET.fromstring(xml_text)
    articles: list[PubMedArticle] = []
    for node in root.findall("./PubmedArticle"):
        citation = node.find("./MedlineCitation")
        article_node = node.find("./MedlineCitation/Article")
        if citation is None or article_node is None:
            continue

        pmid = _node_text(citation.find("./PMID"))
        title = _node_text(article_node.find("./ArticleTitle"))
        if not pmid or not title:
            continue

        abstract = _abstract_text(article_node)
        authors = _unique(_author_name(author) for author in article_node.findall("./AuthorList/Author"))
        organizations = _unique(
            _node_text(affiliation)
            for affiliation in article_node.findall("./AuthorList/Author/AffiliationInfo/Affiliation")
        )
        chemical_names = _unique(
            _node_text(name)
            for name in citation.findall("./ChemicalList/Chemical/NameOfSubstance")
        )
        keywords = _unique(_node_text(keyword) for keyword in citation.findall("./KeywordList/Keyword"))
        mesh_terms = _mesh_terms(citation)
        publication_types = _unique(
            _node_text(publication_type)
            for publication_type in article_node.findall("./PublicationTypeList/PublicationType")
        )
        stage_assessment = infer_development_stage_details(
            title=title,
            abstract=abstract,
            publication_types=publication_types,
            keywords=keywords,
            mesh_terms=mesh_terms,
        )
        combined_text = " ".join(
            part
            for part in (
                title,
                abstract,
                " ".join(keywords),
                " ".join(mesh_terms),
                " ".join(organizations),
            )
            if part
        )
        drugs = _extract_candidate_assets(chemical_names, combined_text)
        targets = _extract_targets(title, abstract, keywords, mesh_terms)
        sponsor_hints = _extract_sponsor_hints(organizations, abstract)
        trial_ids = _extract_trial_ids(combined_text)
        trial_status = _extract_trial_status(combined_text)
        countries = _extract_countries(combined_text, organizations)
        doi = _article_id(node, "doi")

        articles.append(
            PubMedArticle(
                pmid=pmid,
                topic=topic,
                title=title,
                abstract=abstract,
                journal=_node_text(article_node.find("./Journal/Title")) or None,
                published_at=_publication_date(article_node),
                doi=doi,
                authors=authors,
                organizations=organizations,
                drugs=drugs,
                keywords=keywords,
                publication_types=publication_types,
                development_stage=stage_assessment.stage,
                evidence_level=infer_evidence_level(
                    publication_types=publication_types,
                    development_stage=stage_assessment.stage,
                ),
                mesh_terms=mesh_terms,
                targets=targets,
                sponsor_hints=sponsor_hints,
                trial_ids=trial_ids,
                trial_status=trial_status,
                countries=countries,
                development_stage_evidence=stage_assessment.evidence_snippet,
                development_stage_confidence=stage_assessment.confidence,
            )
        )
    return articles


def infer_development_stage(
    *,
    publication_types: list[str],
    abstract: str,
    title: str = "",
    keywords: list[str] | None = None,
    mesh_terms: list[str] | None = None,
) -> str:
    return infer_development_stage_details(
        title=title,
        abstract=abstract,
        publication_types=publication_types,
        keywords=keywords or [],
        mesh_terms=mesh_terms or [],
    ).stage


def infer_development_stage_details(
    *,
    title: str,
    abstract: str,
    publication_types: list[str],
    keywords: list[str],
    mesh_terms: list[str],
) -> DevelopmentStageAssessment:
    sources = [
        ("publication type", item, "high") for item in publication_types if item
    ]
    sources.extend(
        [
            ("title", title, "high"),
            ("abstract", abstract, "high"),
        ]
    )
    sources.extend(("keyword", item, "medium") for item in keywords if item)
    sources.extend(("MeSH", item, "medium") for item in mesh_terms if item)

    for _, text, confidence in sources:
        stage = _highest_explicit_phase(text.lower())
        if stage is not None:
            return DevelopmentStageAssessment(
                stage=stage,
                confidence=confidence,
                evidence_snippet=_clip_evidence(text),
            )

    for _, text, confidence in sources:
        normalized = text.lower()
        if any(marker in normalized for marker in CLINICAL_MARKERS):
            return DevelopmentStageAssessment(
                stage=CLINICAL_STAGE_UNCLEAR,
                confidence=confidence,
                evidence_snippet=_clip_evidence(text),
            )

    preclinical_hits = 0
    preclinical_snippet = ""
    for _, text, confidence in sources:
        normalized = text.lower()
        if any(marker in normalized for marker in PRECLINICAL_MARKERS):
            preclinical_hits += 1
            preclinical_snippet = preclinical_snippet or _clip_evidence(text)
            if confidence == "high":
                return DevelopmentStageAssessment(
                    stage=PRECLINICAL_STAGE,
                    confidence="high",
                    evidence_snippet=preclinical_snippet,
                )
    if preclinical_hits:
        return DevelopmentStageAssessment(
            stage=PRECLINICAL_STAGE,
            confidence="medium" if preclinical_hits > 1 else "low",
            evidence_snippet=preclinical_snippet,
        )

    return DevelopmentStageAssessment(
        stage=UNKNOWN_STAGE,
        confidence="low",
        evidence_snippet=_clip_evidence(title or abstract or "PubMed record did not expose an explicit development-stage clue."),
    )


def infer_evidence_level(
    *,
    publication_types: list[str],
    development_stage: str,
) -> str:
    blob = " ".join(publication_types).lower()
    if "meta-analysis" in blob or "systematic review" in blob:
        return EVIDENCE_SYNTHESIS
    clinical_stages = set(PHASE_LABELS.values()) | {CLINICAL_STAGE_UNCLEAR}
    if development_stage in clinical_stages or "clinical trial" in blob or "randomized controlled trial" in blob:
        return CLINICAL_EVIDENCE
    if "review" in blob:
        return REVIEW_EVIDENCE
    if development_stage == PRECLINICAL_STAGE:
        return PRECLINICAL_EVIDENCE
    return EXPLORATORY_EVIDENCE


def _abstract_text(article_node: ET.Element) -> str:
    abstract_parts: list[str] = []
    for abstract_node in article_node.findall("./Abstract/AbstractText"):
        text = _node_text(abstract_node)
        if not text:
            continue
        label = (abstract_node.attrib.get("Label") or "").strip()
        abstract_parts.append(f"{label}: {text}" if label else text)
    return "\n".join(abstract_parts)


def _mesh_terms(citation: ET.Element) -> list[str]:
    return _unique(
        _node_text(descriptor)
        for descriptor in citation.findall("./MeshHeadingList/MeshHeading/DescriptorName")
    )


def _extract_candidate_assets(chemical_names: list[str], text: str) -> list[str]:
    candidates = list(chemical_names)
    for pattern in ASSET_PATTERNS:
        candidates.extend(match.group(0) for match in pattern.finditer(text))
    result: list[str] = []
    seen: set[str] = set()
    for raw_value in candidates:
        value = _normalize_asset(raw_value)
        if not value:
            continue
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(value)
    return result


def _normalize_asset(value: str) -> str:
    normalized = value.strip().strip(".,;:()[]{}")
    normalized = normalized.replace("™", "").replace("®", "")
    normalized = re.sub(r"\s+", " ", normalized)
    if not normalized:
        return ""
    if normalized.upper() in ASSET_STOPWORDS:
        return ""
    if ASSET_EXCLUDE_PATTERN.fullmatch(normalized):
        return ""
    if re.fullmatch(r"[A-Z]{1,2}", normalized):
        return ""
    return normalized


def _extract_targets(
    title: str,
    abstract: str,
    keywords: list[str],
    mesh_terms: list[str],
) -> list[str]:
    candidates = " ".join([title, abstract, *keywords, *mesh_terms])
    targets: list[str] = []
    seen: set[str] = set()
    if re.search(r"\bEGFR\b", candidates) or re.search(
        r"\bepidermal growth factor receptor\b",
        candidates,
        re.IGNORECASE,
    ):
        seen.add("EGFR")
        targets.append("EGFR")
    for match in TARGET_PATTERN.finditer(candidates):
        value = match.group(0).upper().replace(" ", "")
        if value not in seen:
            seen.add(value)
            targets.append(value)
    return targets


def _extract_sponsor_hints(organizations: list[str], text: str) -> list[str]:
    candidates: list[str] = []
    for organization in organizations:
        candidates.extend(_extract_company_tokens(organization))
    candidates.extend(_extract_company_tokens(text))
    result: list[str] = []
    seen: set[str] = set()
    for raw_value in candidates:
        match = COMPANY_PATTERN.search(raw_value)
        if match is None:
            continue
        value = match.group(1).strip(" ,.;")
        lowered = value.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(value)
    return result


def _extract_company_tokens(text: str) -> list[str]:
    segmented_candidates = [
        segment.strip()
        for segment in re.split(r"[;,\n]", text)
        if segment.strip()
    ]
    matches = [
        match.group(1)
        for segment in segmented_candidates
        for match in COMPANY_PATTERN.finditer(segment)
    ]
    if matches:
        return matches
    return [match.group(1) for match in COMPANY_PATTERN.finditer(text)]


def _extract_trial_ids(text: str) -> list[str]:
    values: list[str] = []
    for pattern in TRIAL_ID_PATTERNS:
        values.extend(match.group(0) for match in pattern.finditer(text))
    return _unique(values)


def _extract_trial_status(text: str) -> str | None:
    normalized = text.lower()
    for status in TRIAL_STATUS_MARKERS:
        if status in normalized:
            return status
    return None


def _extract_countries(text: str, organizations: list[str]) -> list[str]:
    combined = " ".join([text, *organizations])
    hits: list[tuple[int, str]] = []
    for country, pattern in COUNTRY_PATTERNS:
        match = pattern.search(combined)
        if match is not None:
            hits.append((match.start(), country))
    hits.sort(key=lambda item: item[0])
    return _unique(country for _, country in hits)


def _clip_evidence(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1].rstrip()}…"


def _node_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return " ".join("".join(node.itertext()).split())


def _author_name(author: ET.Element) -> str:
    collective = _node_text(author.find("./CollectiveName"))
    if collective:
        return collective
    fore_name = _node_text(author.find("./ForeName"))
    last_name = _node_text(author.find("./LastName"))
    return " ".join(part for part in (fore_name, last_name) if part)


def _article_id(article: ET.Element, id_type: str) -> str | None:
    for article_id in article.findall("./PubmedData/ArticleIdList/ArticleId"):
        if article_id.attrib.get("IdType", "").lower() == id_type.lower():
            value = _node_text(article_id)
            return value or None
    return None


def _publication_date(article: ET.Element) -> datetime | None:
    date_node = article.find("./ArticleDate")
    if date_node is None:
        date_node = article.find("./Journal/JournalIssue/PubDate")
    if date_node is None:
        return None

    year_text = _node_text(date_node.find("./Year"))
    month_text = _node_text(date_node.find("./Month"))
    day_text = _node_text(date_node.find("./Day"))
    if not year_text:
        medline_date = _node_text(date_node.find("./MedlineDate"))
        year_match = re.search(r"\b(19|20)\d{2}\b", medline_date)
        if year_match is None:
            return None
        year_text = year_match.group(0)

    try:
        year = int(year_text)
        month = _month_number(month_text)
        day = int(day_text) if day_text.isdigit() else 1
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


def _month_number(value: str) -> int:
    if value.isdigit():
        return max(1, min(int(value), 12))
    normalized = value.strip().lower()[:3]
    months = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    return months.get(normalized, 1)


def _highest_explicit_phase(blob: str) -> str | None:
    known_phase_tokens = set(PHASE_LABELS)
    tokens: set[str] = set()
    phase_mentions = re.finditer(
        r"\bphase\s+((?:[ivx]+|\d+)[a-z]?(?:\s*(?:/|-|and)\s*(?:[ivx]+|\d+)[a-z]?)*)",
        blob,
        flags=re.IGNORECASE,
    )
    for match in phase_mentions:
        for token in re.findall(r"\b(?:iv|iii|ii|i|4|3|2|1)[a-z]?\b", match.group(1), flags=re.IGNORECASE):
            normalized = token.lower()
            if (
                normalized not in known_phase_tokens
                and len(normalized) > 1
                and normalized[-1].isalpha()
                and normalized[:-1] in known_phase_tokens
            ):
                normalized = normalized[:-1]
            tokens.add(normalized)
    for token in PHASE_ORDER:
        if token in tokens:
            return PHASE_LABELS[token]
    return None


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw_value in values:
        value = str(raw_value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
