import logging
import os
from typing import Any

from app.api.schemas import (
    FacetWeights,
    HardConstraints,
    HardFilters,
    QueryInterpretation,
    RecommendationDebugInfo,
    RecommendationFallback,
    RecommendationMeta,
    RecommendRequest,
    RecommendResponse,
    SoftPreferences,
    SoftTagItem,
    SoftTags,
)
from app.config.similarity_loader import load_all_similarity_tables
from app.db.client import get_db
from app.repositories.product_repository import fetch_candidate_products
from app.services.exploration_service import build_related_ideas
from app.services.ranking_service import (
    compute_soft_score,
    get_facet_weight,
    rank_products,
)
from app.services.reformulation_service import (
    build_global_explanation,
    build_suggested_reformulations,
)
from app.services.similarity_service import build_similarity_ideas

logger = logging.getLogger(__name__)

DEFAULT_RECOMMENDATION_LIMIT = 24
MAX_RECOMMENDATION_LIMIT = 100
RECOMMENDATION_DEFAULT_LIMIT_ENV = "RECOMMENDATION_DEFAULT_LIMIT"
RECOMMENDATION_MAX_LIMIT_ENV = "RECOMMENDATION_MAX_LIMIT"
LEGACY_RECOMMENDATION_LIMIT_ENV = "RECOMMENDATION_RESULT_LIMIT"
KNOWN_FACETS: tuple[str, ...] = ("event", "relationship", "theme", "gift_benefit")
PUBLIC_CONTRACT_VERSION = "recommendation_public_v1"


def _read_positive_int_env(env_name: str, fallback: int) -> int:
    raw_value = os.getenv(env_name)
    if raw_value is None or raw_value.strip() == "":
        return fallback

    try:
        value = int(raw_value.strip())
    except ValueError:
        logger.warning(
            "[Config] Invalid %s=%r; falling back to %s.",
            env_name,
            raw_value,
            fallback,
        )
        return fallback

    if value <= 0:
        logger.warning(
            "[Config] Invalid %s=%r; falling back to %s.",
            env_name,
            raw_value,
            fallback,
        )
        return fallback

    return value


def get_recommendation_max_limit() -> int:
    return _read_positive_int_env(
        RECOMMENDATION_MAX_LIMIT_ENV,
        MAX_RECOMMENDATION_LIMIT,
    )


def get_recommendation_default_limit() -> int:
    max_limit = get_recommendation_max_limit()
    raw_limit = os.getenv(RECOMMENDATION_DEFAULT_LIMIT_ENV)
    if raw_limit is not None and raw_limit.strip() != "":
        return min(
            _read_positive_int_env(
                RECOMMENDATION_DEFAULT_LIMIT_ENV,
                DEFAULT_RECOMMENDATION_LIMIT,
            ),
            max_limit,
        )

    legacy_limit = os.getenv(LEGACY_RECOMMENDATION_LIMIT_ENV)
    if legacy_limit is None or legacy_limit.strip() == "":
        return min(DEFAULT_RECOMMENDATION_LIMIT, max_limit)

    normalized = legacy_limit.strip().lower()
    if normalized in {"0", "all", "none", "unlimited"}:
        logger.warning(
            "[Config] %s=%r is deprecated and unbounded; using %s=%s instead.",
            LEGACY_RECOMMENDATION_LIMIT_ENV,
            legacy_limit,
            RECOMMENDATION_DEFAULT_LIMIT_ENV,
            DEFAULT_RECOMMENDATION_LIMIT,
        )
        return min(DEFAULT_RECOMMENDATION_LIMIT, max_limit)

    try:
        limit = int(legacy_limit.strip())
    except ValueError:
        logger.warning(
            "[Config] Invalid %s=%r; falling back to %s.",
            LEGACY_RECOMMENDATION_LIMIT_ENV,
            legacy_limit,
            DEFAULT_RECOMMENDATION_LIMIT,
        )
        return min(DEFAULT_RECOMMENDATION_LIMIT, max_limit)

    if limit <= 0:
        logger.warning(
            "[Config] Invalid %s=%r; falling back to %s.",
            LEGACY_RECOMMENDATION_LIMIT_ENV,
            legacy_limit,
            DEFAULT_RECOMMENDATION_LIMIT,
        )
        return min(DEFAULT_RECOMMENDATION_LIMIT, max_limit)

    logger.warning(
        "[Config] %s is deprecated; use %s instead.",
        LEGACY_RECOMMENDATION_LIMIT_ENV,
        RECOMMENDATION_DEFAULT_LIMIT_ENV,
    )
    return min(limit, max_limit)


def resolve_pagination(request: RecommendRequest) -> tuple[int, int]:
    max_limit = get_recommendation_max_limit()
    requested_limit = (
        request.limit
        if request.limit is not None
        else get_recommendation_default_limit()
    )

    return min(requested_limit, max_limit), request.offset or 0


def apply_hard_filters(
    products: list[dict[str, Any]],
    hard_filters: HardFilters,
) -> list[dict[str, Any]]:
    """
    Apply blocking hard filters from the request.

    Rules:
    - stock > 0: safety net (already filtered at DB level via repository)
    - age_group: if specified in hard_filters, product must expose at least
      one matching value; products without the field are excluded.
    - recipient_gender: same logic as age_group.

    hard_filters with all fields None => no additional filtering beyond stock.
    """
    result: list[dict[str, Any]] = []
    for p in products:
        # Safety net: exclude zero-stock products
        if p.get("stock", 0) <= 0:
            logger.debug(f"[apply_hard_filters] '{p.get('name')}' excluded: stock=0")
            continue

        # age_group blocking filter
        if hard_filters.age_group:
            product_age_groups: list[str] = p.get("age_group", [])
            if isinstance(product_age_groups, str):
                product_age_groups = [product_age_groups]
            if not set(hard_filters.age_group) & set(product_age_groups):
                logger.debug(
                    f"[apply_hard_filters] '{p.get('name')}' excluded: "
                    f"age_group {product_age_groups!r} not in {hard_filters.age_group!r}"
                )
                continue

        # recipient_gender blocking filter
        if hard_filters.recipient_gender:
            product_genders: list[str] = p.get("recipient_gender", [])
            if isinstance(product_genders, str):
                product_genders = [product_genders]
            if not set(hard_filters.recipient_gender) & set(product_genders):
                logger.debug(
                    f"[apply_hard_filters] '{p.get('name')}' excluded: "
                    f"recipient_gender {product_genders!r} not in {hard_filters.recipient_gender!r}"
                )
                continue

        result.append(p)

    logger.debug(f"[apply_hard_filters] {len(products)} in → {len(result)} out")
    return result

def get_recommendations(request: RecommendRequest) -> list[dict[str, Any]]:
    """
    Recommendation pipeline v2 (Phase 2.5):
      1. Fetch candidate products — DB-level hard filters: optional
         price <= request.budget_max, stock > 0, status == request.status
      2. Apply request-level hard filters: age_group, recipient_gender
      3. Score candidates using soft_tags and facet_weights (Étapes 4-5)
      4. Return all ranked results; pagination is applied by the response layer
    """
    db = get_db()
    collection_name = os.getenv(
        "PRODUCTS_COLLECTION",
        "ProductRecommendationProjection",
    )

    # Step 1: DB-level hard filtering
    #   - price  <= request.budget_max  (budget, when provided)
    #   - stock  >  0              (Decision #7: stock=0 always excluded)
    #   - status == request.status (convention: "active" => eligible)
    products = fetch_candidate_products(
        db,
        budget_max=request.budget_max,
        status=request.status,
        collection_name=collection_name,
    )
    logger.debug(
        f"[Service] {len(products)} products after DB hard filtering "
        f"(collection='{collection_name}', budget_max={request.budget_max}, status='{request.status}')."
    )

    # Step 2: Request-level hard filtering (age_group, recipient_gender)
    products = apply_hard_filters(products, request.hard_filters)
    logger.debug(f"[Service] {len(products)} products after request hard filters.")

    # Step 3: Score candidates using soft_tags × intensity × facet_weight (default=1)
    tables = load_all_similarity_tables()
    products = rank_products(products, request.soft_tags, request.facet_weights, tables)

    logger.debug("[Service] Returning %s ranked recommendations.", len(products))
    return products


def _soft_tag_slugs(soft_tags: SoftTags, facet: str) -> list[str] | None:
    items: list[SoftTagItem] | None = getattr(soft_tags, facet)
    if not items:
        return None
    return [item.slug for item in items]


def _present_facet_weights(facet_weights: FacetWeights) -> dict[str, float]:
    weights: dict[str, float] = {}
    for facet in KNOWN_FACETS:
        value = getattr(facet_weights, facet)
        if value is not None:
            weights[facet] = value
    return weights


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _product_tag_slugs(product: dict[str, Any], facet: str) -> list[str]:
    tags = product.get("tags", {}).get(facet, [])
    return [tag["slug"] for tag in tags if isinstance(tag, dict) and tag.get("slug")]


def _matched_hard_filters(
    product: dict[str, Any],
    hard_filters: HardFilters,
) -> dict[str, list[str]]:
    matches: dict[str, list[str]] = {}
    for facet in ("recipient_gender", "age_group"):
        requested = getattr(hard_filters, facet)
        if not requested:
            continue
        product_values = _as_list(product.get(facet))
        matched = sorted(set(requested) & set(product_values))
        matches[facet] = matched
    return matches


def _matched_soft_tags(product: dict[str, Any], soft_tags: SoftTags) -> dict[str, Any]:
    matches: dict[str, Any] = {}
    for facet in KNOWN_FACETS:
        requested = _soft_tag_slugs(soft_tags, facet)
        if not requested:
            continue
        product_slugs = _product_tag_slugs(product, facet)
        exact_matches = sorted(set(requested) & set(product_slugs))
        matches[facet] = {
            "requested": requested,
            "product_tags": product_slugs,
            "exact_matches": exact_matches,
        }
    return matches


def _with_minimal_explanations(
    products: list[dict[str, Any]],
    request: RecommendRequest,
) -> list[dict[str, Any]]:
    explained: list[dict[str, Any]] = []
    for product in products:
        explained.append(
            {
                **product,
                "_explanation": {
                    "matched_hard_filters": _matched_hard_filters(
                        product,
                        request.hard_filters,
                    ),
                    "matched_soft_tags": _matched_soft_tags(product, request.soft_tags),
                    "score_breakdown": {
                        "total_score": product.get("_score", 0.0),
                        "normalized_score": product.get("score", 0.0),
                        "max_possible_score": product.get("_max_possible_score", 0.0),
                        "detail_level": "minimal_v1",
                        "formula": (
                            "similarity * product_intensity * "
                            "user_intensity * facet_weight"
                        ),
                    },
                },
            }
        )
    return explained


def build_recommendation_response(request: RecommendRequest) -> RecommendResponse:
    """
    Build the public recommendation response without changing engine behavior.

    The scoring pipeline remains delegated to get_recommendations(); this layer
    only exposes the public API contract around the already-ranked matches.
    """
    ranked_matches = _with_minimal_explanations(get_recommendations(request), request)
    total_candidates = len(ranked_matches)
    limit, offset = resolve_pagination(request)
    best_matches = ranked_matches[offset : offset + limit]
    returned_count = len(best_matches)
    has_more = offset + returned_count < total_candidates
    next_offset = offset + returned_count if has_more else None

    explanation = build_global_explanation(request)
    top_score = best_matches[0].get("score", 0.0) if best_matches else None
    suggested_reformulations = build_suggested_reformulations(
        request,
        result_count=returned_count,
        top_score=top_score,
    )
    similarity_ideas = build_similarity_ideas(
        best_matches,
        ranked_matches,
        load_all_similarity_tables(),
    )
    related_ideas = build_related_ideas(request)

    detected_signals: dict[str, Any] = {}
    if request.budget_max is not None:
        detected_signals["budget_max"] = request.budget_max
    for facet in KNOWN_FACETS:
        slugs = _soft_tag_slugs(request.soft_tags, facet)
        if slugs:
            detected_signals[facet] = slugs
    if request.hard_filters.recipient_gender:
        detected_signals["recipient_gender"] = request.hard_filters.recipient_gender
    if request.hard_filters.age_group:
        detected_signals["age_group"] = request.hard_filters.age_group

    query_interpretation = QueryInterpretation(
        normalized_query=None,
        detected_signals=detected_signals,
        confidence={},
    )
    hard_constraints = HardConstraints(
        status=request.status,
        budget_max=request.budget_max,
        availability="in_stock",
        recipient_gender=request.hard_filters.recipient_gender,
        age_group=request.hard_filters.age_group,
    )
    soft_preferences = SoftPreferences(
        event=_soft_tag_slugs(request.soft_tags, "event"),
        relationship=_soft_tag_slugs(request.soft_tags, "relationship"),
        theme=_soft_tag_slugs(request.soft_tags, "theme"),
        gift_benefit=_soft_tag_slugs(request.soft_tags, "gift_benefit"),
        facet_weights=_present_facet_weights(request.facet_weights),
    )
    fallback = None
    if total_candidates == 0:
        fallback = RecommendationFallback(
            reason="no_matches",
            message="Aucun produit ne correspond aux contraintes actuelles.",
        )

    return RecommendResponse(
        total_candidates=total_candidates,
        returned_count=returned_count,
        limit=limit,
        offset=offset,
        has_more=has_more,
        next_offset=next_offset,
        query_interpretation=query_interpretation,
        hard_constraints=hard_constraints,
        soft_preferences=soft_preferences,
        best_matches=best_matches,
        similarity_ideas=similarity_ideas,
        explanation=explanation,
        related_ideas=related_ideas,
        relaxations_applied=[],
        suggested_reformulations=suggested_reformulations,
        fallback=fallback,
        meta=RecommendationMeta(
            result_count=returned_count,
            limit=limit,
            offset=offset,
            total_candidates=total_candidates,
            returned_count=returned_count,
            has_more=has_more,
            next_offset=next_offset,
            contract_version=PUBLIC_CONTRACT_VERSION,
        ),
        debug_info=RecommendationDebugInfo(
            scoring_formula="similarity * product_intensity * user_intensity * facet_weight",
            stock_filter="stock > 0",
            exact_match_score=1.0,
            suggestion_builder_enabled=False,
            phase="post_refactor_v1",
        ),
    )
