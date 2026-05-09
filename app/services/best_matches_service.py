import logging
from typing import Any

from app.config.similarity_loader import load_all_similarity_tables
from app.core.architecture_guard import (
    FORBIDDEN_FIELDS,
    assert_service_call_allowed,
    assert_no_scoring_outside_best_matches,
)
from app.schemas.recommendation import RecommendationRequest

logger = logging.getLogger(__name__)

KNOWN_FACETS: tuple[str, ...] = ("event", "relationship", "theme", "gift_benefit")


def _soft_tag_items(soft_tags: dict[str, Any] | None, facet: str) -> list[dict[str, Any]]:
    if not soft_tags:
        return []
    raw_items = soft_tags.get(facet)
    if not isinstance(raw_items, list):
        return []

    items: list[dict[str, Any]] = []
    for item in raw_items:
        if isinstance(item, dict) and isinstance(item.get("slug"), str):
            items.append(
                {
                    "slug": item["slug"],
                    "intensity": float(item.get("intensity", 1.0)),
                }
            )
        elif isinstance(item, str):
            items.append({"slug": item, "intensity": 1.0})
    return items


def _facet_weight(facet_weights: dict[str, Any] | None, facet: str) -> float:
    if not facet_weights or facet not in facet_weights:
        return 1.0
    return float(facet_weights[facet])


def _known_similarity_slugs(table: dict[str, dict[str, float]]) -> set[str]:
    return set(table) | {slug for row in table.values() for slug in row}


def _best_similarity_contribution(
    user_slug: str,
    product_tags: list[dict[str, Any]],
    table: dict[str, dict[str, float]],
) -> tuple[float, float]:
    if not product_tags:
        return 0.0, 0.0

    known_slugs = _known_similarity_slugs(table)
    if user_slug not in known_slugs:
        raise ValueError(f"unknown similarity slug '{user_slug}'")

    row = table.get(user_slug, {})
    best_similarity = 0.0
    best_product_intensity = 0.0
    for tag in product_tags:
        if not isinstance(tag, dict) or not tag.get("slug"):
            continue
        product_slug = str(tag["slug"])
        if product_slug not in known_slugs:
            raise ValueError(f"unknown similarity slug '{product_slug}'")
        similarity = float(row.get(product_slug, 0.0))
        product_intensity = float(tag.get("intensity", 1.0))
        contribution = similarity * product_intensity
        if contribution > best_similarity * best_product_intensity:
            best_similarity = similarity
            best_product_intensity = product_intensity
    return best_similarity, best_product_intensity


def _raw_score(
    product: dict[str, Any],
    request: RecommendationRequest,
    tables: dict[str, dict[str, dict[str, float]]],
) -> float:
    score = 0.0
    for facet in KNOWN_FACETS:
        product_tags = product.get("tags", {}).get(facet, [])
        if not isinstance(product_tags, list):
            product_tags = []

        facet_weight = _facet_weight(request.facet_weights, facet)
        table = tables.get(facet, {})

        best_facet_score = 0.0
        for user_tag in _soft_tag_items(request.soft_tags, facet):
            similarity, product_intensity = _best_similarity_contribution(
                user_tag["slug"],
                product_tags,
                table,
            )
            user_intensity = float(user_tag["intensity"])
            contribution = similarity * product_intensity * user_intensity * facet_weight
            best_facet_score = max(best_facet_score, contribution)
        score += best_facet_score
    return score


def _max_possible_score(request: RecommendationRequest) -> float:
    total = 0.0
    for facet in KNOWN_FACETS:
        items = _soft_tag_items(request.soft_tags, facet)
        if not items:
            continue
        total += max(item["intensity"] for item in items) * _facet_weight(
            request.facet_weights,
            facet,
        )
    return total


def _product_id(product: dict[str, Any]) -> str:
    return str(product.get("product_id", product.get("_id", product.get("name", ""))))


def _build_reason(
    product: dict[str, Any],
    request: RecommendationRequest,
    tables: dict[str, dict[str, dict[str, float]]],
) -> str:
    matched_facets: dict[str, str] = {}
    
    for facet in KNOWN_FACETS:
        product_tags = product.get("tags", {}).get(facet, [])
        if not isinstance(product_tags, list):
            product_tags = []
            
        table = tables.get(facet, {})
        best_contribution = 0.0
        best_user_slug = None
        
        for user_tag in _soft_tag_items(request.soft_tags, facet):
            try:
                similarity, product_intensity = _best_similarity_contribution(
                    user_tag["slug"],
                    product_tags,
                    table,
                )
            except ValueError:
                continue
                
            contribution = similarity * product_intensity
            if contribution > best_contribution and contribution > 0:
                best_contribution = contribution
                best_user_slug = user_tag["slug"]
                
        if best_user_slug:
            matched_facets[facet] = best_user_slug.replace("_", " ")
            
    if "theme" in matched_facets and "event" in matched_facets:
        return f"Correspond au thème {matched_facets['theme']} et à l'occasion {matched_facets['event']}."
    elif "event" in matched_facets:
        return f"Idéal pour l'occasion {matched_facets['event']}."
    elif "relationship" in matched_facets:
        return f"Adapté à un cadeau pour {matched_facets['relationship']}."
    elif "theme" in matched_facets:
        return f"Correspond au style {matched_facets['theme']} recherché."
    elif "gift_benefit" in matched_facets:
        return f"Offre l'avantage {matched_facets['gift_benefit']}."
    
    return "Ce cadeau correspond à votre recherche."


def _without_forbidden_fields(product: dict[str, Any]) -> dict[str, Any]:
    forbidden = set(FORBIDDEN_FIELDS)
    return {
        key: value
        for key, value in product.items()
        if key not in forbidden
    }


def best_matches_service(
    candidate_generation: dict[str, Any],
    request: RecommendationRequest,
) -> list[dict[str, Any]]:
    assert_service_call_allowed("best_matches")
    assert_no_scoring_outside_best_matches()
    candidates = candidate_generation.get("_candidates", [])
    logger.debug(
        "[best_matches] ENTER — %d candidates received (limit=%d, offset=%d).",
        len(candidates),
        request.limit,
        request.offset,
    )
    tables = load_all_similarity_tables()
    max_possible_score = _max_possible_score(request)
    logger.debug("[best_matches] max_possible_score=%.4f", max_possible_score)

    scored: list[dict[str, Any]] = []
    for product in candidates:
        raw_score = _raw_score(product, request, tables)
        normalized_score = 0.0 if max_possible_score <= 0 else raw_score / max_possible_score
        normalized_score = max(0.0, min(1.0, normalized_score))
        scored.append(
            {
                **_without_forbidden_fields(product),
                "product_id": _product_id(product),
                "score": normalized_score,
                "reason": _build_reason(product, request, tables),
            }
        )

    scored.sort(key=lambda product: (-product["score"], _product_id(product)))
    logger.debug(
        "[best_matches] %d products scored and sorted.",
        len(scored),
    )
    logger.debug(
        "[best_matches] Scored product IDs (all): %s",
        [_product_id(p) for p in scored],
    )
    page = scored[request.offset : request.offset + request.limit]
    logger.debug(
        "[best_matches] SLICE [%d:%d] → %d products returned to response.",
        request.offset,
        request.offset + request.limit,
        len(page),
    )
    logger.debug(
        "[best_matches] Returned product IDs: %s",
        [_product_id(p) for p in page],
    )
    return page
