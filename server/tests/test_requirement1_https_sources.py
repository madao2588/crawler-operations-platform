from urllib.parse import urlparse

from app.services.template_service import (
    NEW_DRUG_SOURCE_TEMPLATES,
    PROJECT_DECLARATION_ENABLED_TEMPLATE_IDS,
)


def test_government_sources_use_https_or_documented_http_fallbacks() -> None:
    sources = {
        str(item["id"]): str(item["start_url"])
        for item in NEW_DRUG_SOURCE_TEMPLATES
        if item["id"] in PROJECT_DECLARATION_ENABLED_TEMPLATE_IDS
    }

    assert set(sources) == PROJECT_DECLARATION_ENABLED_TEMPLATE_IDS
    http_fallbacks = {
        source_id
        for source_id, url in sources.items()
        if urlparse(url).scheme == "http"
    }
    assert http_fallbacks == {
        "hunan_stc_notices",
        "changsha_sti_notices",
    }
    assert all(urlparse(url).scheme in {"http", "https"} for url in sources.values())


def test_government_sources_are_staggered_to_avoid_browser_burst() -> None:
    crons = [
        str(item["cron_expr"])
        for item in NEW_DRUG_SOURCE_TEMPLATES
        if item["id"] in PROJECT_DECLARATION_ENABLED_TEMPLATE_IDS
    ]

    assert len(crons) == len(PROJECT_DECLARATION_ENABLED_TEMPLATE_IDS)
    assert len(set(crons)) == len(crons)
    assert all(cron.split()[1] == "8,14" for cron in crons)
