from typing import Any

from app.config.facets import SIMILARITY_FACETS
from app.core.architecture_guard import assert_service_call_allowed
from app.schemas.recommendation import RecommendationRequest

SOFT_SIGNAL_ORDER: tuple[str, ...] = SIMILARITY_FACETS


def _slugs_from_soft_tags(soft_tags: dict[str, Any] | None, facet: str) -> list[str]:
    if not soft_tags:
        return []
    raw_items = soft_tags.get(facet)
    if not isinstance(raw_items, list):
        return []

    slugs: list[str] = []
    for item in raw_items:
        if isinstance(item, dict) and isinstance(item.get("slug"), str):
            slugs.append(item["slug"])
        elif isinstance(item, str):
            slugs.append(item)
    return slugs


def query_understanding_service(request: RecommendationRequest) -> dict[str, Any]:
    assert_service_call_allowed("query_understanding")
    detected_signals = {
        facet: _slugs_from_soft_tags(request.soft_tags, facet)
        for facet in SOFT_SIGNAL_ORDER
    }
    missing_signals = [
        facet for facet, slugs in detected_signals.items() if not slugs
    ]

    return {
        "detected_signals": detected_signals,
        "confidence": {},
        "missing_signals": missing_signals,
    }
