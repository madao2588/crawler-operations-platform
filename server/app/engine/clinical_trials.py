from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Awaitable, Callable
from urllib.parse import urlencode
from urllib.request import urlopen

from app.engine.pubmed import _extract_targets, _unique


CLINICAL_TRIALS_V2_BASE_URL = "https://clinicaltrials.gov/api/v2/studies"
CLINICAL_TRIALS_STUDY_BASE_URL = "https://clinicaltrials.gov/study"
PHASE_ORDER = ("PHASE4", "PHASE3", "PHASE2", "PHASE1", "EARLY_PHASE1")
TOPIC_CONTRACTS = (
    (
        ("脑胶质瘤", "胶质瘤", "glioma", "glioblastoma"),
        (
            "脑胶质瘤",
            "胶质瘤",
            "胶质母细胞瘤",
            "glioma",
            "glioblastoma",
            "astrocytoma",
        ),
    ),
    (
        ("降尿酸药物", "高尿酸", "痛风", "hyperuricemia", "gout", "urate"),
        (
            "降尿酸",
            "高尿酸",
            "痛风",
            "尿酸",
            "hyperuricemia",
            "hyperuricaemia",
            "gout",
            "gouty",
            "urate",
            "uric acid",
            "xanthine oxidase",
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class ClinicalTrialStudy:
    nct_id: str
    brief_title: str
    official_title: str
    brief_summary: str
    phase: str | None
    status: str | None
    sponsor: str | None
    collaborators: list[str]
    conditions: list[str]
    interventions: list[str]
    drug_assets: list[str]
    targets: list[str]
    trial_ids: list[str]
    countries: list[str]
    keywords: list[str]
    study_url: str | None


@dataclass(frozen=True, slots=True)
class ClinicalTrialsSearchPage:
    studies: list[ClinicalTrialStudy]
    next_page_token: str | None


class ClinicalTrialsGovClient:
    def __init__(
        self,
        *,
        fetch_json: Callable[[str], Awaitable[dict[str, object]]] | None = None,
    ) -> None:
        self._fetch_json = fetch_json or _fetch_json_from_api

    async def search_studies(
        self,
        *,
        query_term: str | None = None,
        query_condition: str | None = None,
        intervention_type: str | None = None,
        page_size: int = 10,
        page_token: str | None = None,
    ) -> ClinicalTrialsSearchPage:
        params = {"pageSize": str(max(1, min(int(page_size), 100)))}
        normalized_term = (query_term or "").strip()
        normalized_condition = (query_condition or "").strip()
        if normalized_term:
            params["query.term"] = normalized_term
        if normalized_condition:
            params["query.cond"] = normalized_condition
        if not normalized_term and not normalized_condition:
            raise ValueError("ClinicalTrials.gov search requires a term or condition")
        normalized_intervention_type = (intervention_type or "").strip().upper()
        if normalized_intervention_type:
            if not normalized_intervention_type.replace("_", "").isalpha():
                raise ValueError("Invalid ClinicalTrials.gov intervention type")
            params["filter.advanced"] = (
                f"AREA[InterventionType]{normalized_intervention_type}"
            )
        if page_token:
            params["pageToken"] = page_token
        payload = await self._fetch_json(f"{CLINICAL_TRIALS_V2_BASE_URL}?{urlencode(params)}")
        raw_studies = payload.get("studies", []) if isinstance(payload, dict) else []
        studies = [
            parse_clinical_trial_study(item)
            for item in raw_studies
            if isinstance(item, dict)
        ]
        next_page_token = None
        if isinstance(payload, dict):
            token = payload.get("nextPageToken")
            if isinstance(token, str) and token.strip():
                next_page_token = token.strip()
        return ClinicalTrialsSearchPage(
            studies=studies,
            next_page_token=next_page_token,
        )


def parse_clinical_trial_study(raw_study: dict[str, object]) -> ClinicalTrialStudy:
    protocol = _mapping(raw_study.get("protocolSection"))
    identification = _mapping(protocol.get("identificationModule"))
    status_module = _mapping(protocol.get("statusModule"))
    sponsor_module = _mapping(protocol.get("sponsorCollaboratorsModule"))
    description_module = _mapping(protocol.get("descriptionModule"))
    conditions_module = _mapping(protocol.get("conditionsModule"))
    design_module = _mapping(protocol.get("designModule"))
    interventions_module = _mapping(protocol.get("armsInterventionsModule"))
    contacts_module = _mapping(protocol.get("contactsLocationsModule"))

    nct_id = _text(identification.get("nctId"))
    brief_title = _text(identification.get("briefTitle"))
    official_title = _text(identification.get("officialTitle"))
    brief_summary = _text(description_module.get("briefSummary"))
    phase = _best_phase(_strings(design_module.get("phases")))
    status = _normalize_status(_text(status_module.get("overallStatus")))
    sponsor = _text(_mapping(sponsor_module.get("leadSponsor")).get("name")) or None
    collaborators = _unique(
        _text(_mapping(item).get("name"))
        for item in _sequence(sponsor_module.get("collaborators"))
    )
    conditions = _strings(conditions_module.get("conditions"))
    keywords = _strings(conditions_module.get("keywords"))

    interventions_payload = _sequence(interventions_module.get("interventions"))
    interventions = _unique(_text(_mapping(item).get("name")) for item in interventions_payload)
    drug_assets = _unique(
        value
        for item in interventions_payload
        for value in _drug_asset_values(_mapping(item))
    )
    targets = _extract_targets(
        brief_title,
        brief_summary,
        keywords,
        [],
    )
    trial_ids = _unique(
        [
            nct_id,
            *(
                _text(_mapping(item).get("id"))
                for item in _sequence(identification.get("secondaryIdInfos"))
                if _is_registry_trial_id(_mapping(item))
            ),
        ]
    )
    countries = _unique(
        _text(_mapping(item).get("country"))
        for item in _sequence(contacts_module.get("locations"))
    )
    study_url = f"{CLINICAL_TRIALS_STUDY_BASE_URL}/{nct_id}" if nct_id else None

    return ClinicalTrialStudy(
        nct_id=nct_id,
        brief_title=brief_title,
        official_title=official_title,
        brief_summary=brief_summary,
        phase=phase,
        status=status,
        sponsor=sponsor,
        collaborators=collaborators,
        conditions=conditions,
        interventions=interventions,
        drug_assets=drug_assets,
        targets=targets,
        trial_ids=trial_ids,
        countries=countries,
        keywords=keywords,
        study_url=study_url,
    )


def is_study_relevant_to_topic(study: ClinicalTrialStudy, topic: str) -> bool:
    return is_clinical_trial_text_relevant(
        topic,
        (
            study.brief_title,
            study.official_title,
            study.brief_summary,
            *study.conditions,
            *study.keywords,
            *study.interventions,
            *study.drug_assets,
        ),
    )


def is_clinical_trial_text_relevant(
    topic: str,
    values: Iterable[object],
) -> bool:
    """Apply the fixed requirement-3 topic contract to API or stored text."""
    normalized_topic = _normalize_search_text(topic)
    if not normalized_topic:
        return False

    terms: tuple[str, ...] | None = None
    for aliases, contract_terms in TOPIC_CONTRACTS:
        if any(_normalize_search_text(alias) in normalized_topic for alias in aliases):
            terms = contract_terms
            break
    if terms is None:
        terms = (normalized_topic,)

    corpus = f" {' '.join(_normalize_search_text(value) for value in values)} "
    return any(
        f" {_normalize_search_text(term)} " in corpus
        or (
            not _normalize_search_text(term).isascii()
            and _normalize_search_text(term) in corpus
        )
        for term in terms
        if _normalize_search_text(term)
    )


async def _fetch_json_from_api(url: str) -> dict[str, object]:
    return await asyncio.to_thread(_load_json, url)


def _load_json(url: str) -> dict[str, object]:
    with urlopen(url, timeout=20) as response:  # noqa: S310 - trusted public API helper
        payload = json.load(response)
    if not isinstance(payload, dict):
        return {}
    return payload


def _best_phase(phases: list[str]) -> str | None:
    normalized = {phase.strip().upper(): phase.strip().upper() for phase in phases if phase.strip()}
    for candidate in PHASE_ORDER:
        if candidate in normalized:
            return _normalize_phase(candidate)
    if phases:
        return _normalize_phase(phases[0])
    return None


def _normalize_phase(value: str) -> str:
    mapping = {
        "PHASE4": "Phase 4",
        "PHASE3": "Phase 3",
        "PHASE2": "Phase 2",
        "PHASE1": "Phase 1",
        "EARLY_PHASE1": "Early Phase 1",
    }
    return mapping.get(value.strip().upper(), value.strip())


def _normalize_status(value: str) -> str | None:
    normalized = value.strip()
    if not normalized:
        return None
    return normalized.lower().replace("_", " ")


def _drug_asset_values(intervention: dict[str, object]) -> list[str]:
    values: list[str] = []
    if _text(intervention.get("type")).upper() == "DRUG":
        values.extend(_asset_names(intervention.get("name")))
        for other_name in _strings(intervention.get("otherNames")):
            values.extend(_asset_names(other_name))
    return _unique(values)


def _asset_names(value: object) -> list[str]:
    return _unique(part.strip() for part in _text(value).split(";"))


def _is_registry_trial_id(item: dict[str, object]) -> bool:
    identifier = _text(item.get("id"))
    id_type = _text(item.get("type")).upper()
    if not identifier:
        return False
    if id_type in {"EUDRACT_NUMBER", "CTRI", "CHICTR"}:
        return True
    return identifier.upper().startswith("NCT")


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _strings(value: object) -> list[str]:
    return _unique(_text(item) for item in _sequence(value))


def _mapping(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _sequence(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _normalize_search_text(value: object) -> str:
    return re.sub(r"[\W_]+", " ", _text(value).casefold()).strip()
