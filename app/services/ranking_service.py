import logging
import math
from typing import Any

from app.api.schemas import FacetWeights, SoftTagItem, SoftTags
from app.config.facets import SIMILARITY_FACETS, SOFT_FACET_DEFAULT_WEIGHTS
from app.services.matcher import compute_match

logger = logging.getLogger(__name__)

KNOWN_FACETS: tuple[str, ...] = SIMILARITY_FACETS


def get_facet_weight(facet_weights: FacetWeights, facet: str) -> float:
    raw_weight: float | None = getattr(facet_weights, facet, None)
    weight: float = (
        raw_weight
        if raw_weight is not None
        else SOFT_FACET_DEFAULT_WEIGHTS.get(facet, 1.0)
    )
    if not math.isfinite(weight):
        raise ValueError(f"facet_weights.{facet} must be finite")
    return weight


def compute_max_possible_score(
    soft_tags: SoftTags,
    facet_weights: FacetWeights,
) -> float:
    total = 0.0
    for facet in KNOWN_FACETS:
        user_soft_tags: list[SoftTagItem] | None = getattr(soft_tags, facet, None)
        if not user_soft_tags:
            continue
        max_user_intensity = max(item.intensity for item in user_soft_tags)
        total += max_user_intensity * get_facet_weight(facet_weights, facet)
    return total


def normalize_score(score: float, max_possible_score: float) -> float:
    if max_possible_score <= 0:
        return 0.0
    normalized = score / max_possible_score
    return max(0.0, min(1.0, normalized))


def compute_soft_score(
    product: dict[str, Any],
    soft_tags: SoftTags,
    facet_weights: FacetWeights,
    tables: dict[str, dict[str, dict[str, float]]],
) -> float:
    """
    Multi-facet raw score driven by soft_tags and facet_weights from the request.

    Formula per facet:
        facet_score = max(
            compute_match(user_tag.slug, product.tags[facet], table)
            * user_tag.intensity
            * facet_weight
            for user_tag in soft_tags[facet]
        )
    total_score = sum(facet_score for all facets)
    """
    product_tags: dict[str, list[dict[str, Any]]] = product.get("tags", {})
    total: float = 0.0

    for facet in KNOWN_FACETS:
        user_soft_tags: list[SoftTagItem] | None = getattr(soft_tags, facet, None)
        if not user_soft_tags:
            logger.debug(
                "[Scoring] %r | facet=%r -> no user soft_tags, skipped",
                product.get("name"),
                facet,
            )
            continue

        weight = get_facet_weight(facet_weights, facet)
        facet_tags: list[dict[str, Any]] = product_tags.get(facet, [])
        table: dict[str, dict[str, float]] = tables.get(facet, {})

        best_facet: float = 0.0
        for user_tag in user_soft_tags:
            match: float = compute_match(user_tag.slug, facet_tags, table)
            contribution: float = match * user_tag.intensity * weight
            logger.debug(
                "[Scoring] %r | facet=%r user_slug=%r intensity=%.3f "
                "weight=%.3f match=%.4f contribution=%.4f",
                product.get("name"),
                facet,
                user_tag.slug,
                user_tag.intensity,
                weight,
                match,
                contribution,
            )
            if contribution > best_facet:
                best_facet = contribution

        total += best_facet
        logger.debug(
            "[Scoring] %r | facet=%r weight=%.3f best=%.4f",
            product.get("name"),
            facet,
            weight,
            best_facet,
        )

    logger.debug("[Scoring] %r -> raw score=%.4f", product.get("name"), total)
    return total


def _product_identifier(product: dict[str, Any]) -> str:
    return str(product.get("product_id", product.get("_id", product.get("name", ""))))


def _score_reason(product: dict[str, Any], soft_tags: SoftTags) -> str:
    matched_facets: list[str] = []
    product_tags = product.get("tags", {})
    for facet in KNOWN_FACETS:
        requested_items: list[SoftTagItem] | None = getattr(soft_tags, facet, None)
        if not requested_items:
            continue
        requested = {item.slug for item in requested_items}
        product_slugs = {
            tag.get("slug")
            for tag in product_tags.get(facet, [])
            if isinstance(tag, dict) and tag.get("slug")
        }
        exact = sorted(requested & product_slugs)
        if exact:
            matched_facets.append(f"{facet}: {', '.join(exact)}")

    if matched_facets:
        return "Matches " + "; ".join(matched_facets) + "."
    if product.get("_score", 0.0) > 0:
        return "Matches the request through configured similarity tables."
    return "Eligible product after hard constraints."


def rank_products(
    products: list[dict[str, Any]],
    soft_tags: SoftTags,
    facet_weights: FacetWeights,
    tables: dict[str, dict[str, dict[str, float]]],
) -> list[dict[str, Any]]:
    """
    Score every product once with compute_soft_score and return a deterministic list.

    `_score` remains the raw internal score for backward compatibility.
    `score` is the normalized public score in [0, 1].
    """
    max_possible = compute_max_possible_score(soft_tags, facet_weights)
    scored: list[dict[str, Any]] = []
    for product in products:
        raw_score = compute_soft_score(product, soft_tags, facet_weights, tables)
        normalized_score = normalize_score(raw_score, max_possible)
        scored_product = {
            **product,
            "product_id": str(
                product.get("product_id", product.get("_id", product.get("name", "")))
            ),
            "_score": raw_score,
            "_raw_score": raw_score,
            "_max_possible_score": max_possible,
            "score": normalized_score,
        }
        scored_product["reason"] = _score_reason(scored_product, soft_tags)
        scored.append(scored_product)

    scored.sort(key=lambda product: (-product["score"], _product_identifier(product)))
    logger.debug("[rank_products] Ranked %s products with single ranking engine.", len(scored))
    return scored
