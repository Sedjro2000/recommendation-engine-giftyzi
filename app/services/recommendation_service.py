import logging
import math
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
from app.services.matcher import compute_match

logger = logging.getLogger(__name__)

TOP_N = 10
KNOWN_FACETS: tuple[str, ...] = ("event", "relationship", "theme", "gift_benefit")
NEUTRAL_FACET_WEIGHT = 1.0
PUBLIC_CONTRACT_VERSION = "recommendation_public_v1"


def get_facet_weight(facet_weights: FacetWeights, facet: str) -> float:
    """
    Return the request-provided facet weight or the explicit neutral fallback.

    Next.js is the source of truth for facet weights. When a SOFT facet is used
    but its weight is absent from the payload, FastAPI applies the neutral
    fallback 1.0. The fallback is never 0.
    """
    raw_weight: float | None = getattr(facet_weights, facet, None)
    weight: float = raw_weight if raw_weight is not None else NEUTRAL_FACET_WEIGHT
    if not math.isfinite(weight):
        raise ValueError(f"facet_weights.{facet} must be finite")
    return weight


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


def compute_soft_score(
    product: dict[str, Any],
    soft_tags: SoftTags,
    facet_weights: FacetWeights,
    tables: dict[str, dict[str, dict[str, float]]],
) -> float:
    """
    Multi-facet score driven by soft_tags and facet_weights from the request.

    Formula per facet:
        facet_score = max(
            compute_match(user_tag.slug, product.tags[facet], table)
            * user_tag.intensity
            * facet_weight
            for user_tag in soft_tags[facet]
        )
    total_score = sum(facet_score for all facets)

    Rules:
    - soft_tags absent for a facet  => facet contributes 0
    - product has no tags for facet => match = 0, facet contributes 0
    - intensity influences score proportionally
    - facet_weight absent in request  => default 1.0
    - facet_weight = 0 explicitly     => facet contributes 0
    - soft_tags are NEVER used as hard filters
    """
    product_tags: dict[str, list[dict[str, Any]]] = product.get("tags", {})
    total: float = 0.0

    for facet in KNOWN_FACETS:
        user_soft_tags: list[SoftTagItem] | None = getattr(soft_tags, facet, None)
        if not user_soft_tags:
            logger.debug(
                f"[Scoring] '{product.get('name')}' | facet='{facet}' → no user soft_tags, skipped"
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
                f"[Scoring] '{product.get('name')}' | facet='{facet}' "
                f"user_slug='{user_tag.slug}' intensity={user_tag.intensity} "
                f"weight={weight} match={match:.4f} contribution={contribution:.4f}"
            )
            if contribution > best_facet:
                best_facet = contribution

        total += best_facet
        logger.debug(
            f"[Scoring] '{product.get('name')}' | facet='{facet}' "
            f"weight={weight} best={best_facet:.4f}"
        )

    logger.debug(f"[Scoring] '{product.get('name')}' → total score={total:.4f}")
    return total


def rank_products(
    products: list[dict[str, Any]],
    soft_tags: SoftTags,
    facet_weights: FacetWeights,
    tables: dict[str, dict[str, dict[str, float]]],
) -> list[dict[str, Any]]:
    """
    Score every product with compute_soft_score and return a deterministic sorted list.

    Sort key (tuple, ascending):
        1. -_score           → highest score first
        2. str(_id or name)  → stable tie-breaker; _id (MongoDB ObjectId as string)
                               takes priority; falls back to name for in-memory data.

    Guarantees:
    - Same input always produces same output (no random, no dict-order dependency)
    - Equal scores resolved by _id ascending (lexicographic)
    - No external randomness used
    """
    scored = [
        {**p, "_score": compute_soft_score(p, soft_tags, facet_weights, tables)}
        for p in products
    ]
    scored.sort(
        key=lambda p: (
            -p["_score"],
            str(p.get("_id", p.get("name", ""))),
        )
    )
    logger.debug(f"[rank_products] Ranked {len(scored)} products.")
    return scored


def get_recommendations(request: RecommendRequest) -> list[dict[str, Any]]:
    """
    Recommendation pipeline v2 (Phase 2.5):
      1. Fetch candidate products — DB-level hard filters: price <= request.price,
         stock > 0, status == request.status
      2. Apply request-level hard filters: age_group, recipient_gender
      3. Score candidates using soft_tags and facet_weights (Étapes 4-5)
      4. Return top N results, sorted by score descending
    """
    db = get_db()
    collection_name = os.getenv("PRODUCTS_COLLECTION", "products")

    # Step 1: DB-level hard filtering
    #   - price  <= request.price  (budget)
    #   - stock  >  0              (Decision #7: stock=0 always excluded)
    #   - status == request.status (convention: "active" => eligible)
    products = fetch_candidate_products(
        db,
        budget_max=request.price,
        status=request.status,
        collection_name=collection_name,
    )
    logger.debug(
        f"[Service] {len(products)} products after DB hard filtering "
        f"(collection='{collection_name}', price<={request.price}, status='{request.status}')."
    )

    # Step 2: Request-level hard filtering (age_group, recipient_gender)
    products = apply_hard_filters(products, request.hard_filters)
    logger.debug(f"[Service] {len(products)} products after request hard filters.")

    # Step 3: Score candidates using soft_tags × intensity × facet_weight (default=1)
    tables = load_all_similarity_tables()
    products = rank_products(products, request.soft_tags, request.facet_weights, tables)

    top = products[:TOP_N]
    logger.debug(f"[Service] Returning top {len(top)} recommendations (TOP_N={TOP_N}).")
    return top


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
    best_matches = _with_minimal_explanations(get_recommendations(request), request)

    detected_signals: dict[str, Any] = {
        "budget_max": request.price,
    }
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
        budget_max=request.price,
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
    if not best_matches:
        fallback = RecommendationFallback(
            reason="no_matches",
            message="Aucun produit ne correspond aux contraintes actuelles.",
        )

    return RecommendResponse(
        query_interpretation=query_interpretation,
        hard_constraints=hard_constraints,
        soft_preferences=soft_preferences,
        best_matches=best_matches,
        related_ideas=[],
        relaxations_applied=[],
        suggested_reformulations=[],
        fallback=fallback,
        meta=RecommendationMeta(
            result_count=len(best_matches),
            limit=TOP_N,
            contract_version=PUBLIC_CONTRACT_VERSION,
        ),
        debug_info=RecommendationDebugInfo(
            scoring_formula="similarity * product_intensity * user_intensity * facet_weight",
            stock_filter="stock > 0",
            exact_match_score=1.0,
        ),
    )
