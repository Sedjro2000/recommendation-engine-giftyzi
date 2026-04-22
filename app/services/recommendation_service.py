import logging
import os
from typing import Any

from app.config.similarity_loader import load_all_similarity_tables
from app.db.client import get_db
from app.repositories.product_repository import fetch_candidate_products
from app.services.explainer import FACET_WEIGHTS, build_explanation
from app.services.matcher import compute_match
from app.services.query_interpreter import QueryContext, interpret_query

logger = logging.getLogger(__name__)

TOP_N = 10


def compute_score(
    product: dict[str, Any],
    context: QueryContext,
    tables: dict[str, dict[str, dict[str, float]]],
) -> float:
    """
    Multi-facet score: score = Σ (weight × match_facet)

    Fallback: if the product has no 'tags' field but has a legacy 'occasion_score',
    the legacy scoring logic is applied to preserve backward compatibility during
    the transition period (before Step 5 migrates product data to structured tags).
    """
    product_tags: dict[str, list[dict[str, Any]]] = product.get("tags", {})

    if not product_tags and "occasion_score" in product:
        # ── Legacy fallback ────────────────────────────────────────────────────
        occasion_scores: dict[str, float] = product["occasion_score"]
        event = context.get("event")
        if event and event in occasion_scores:
            score = occasion_scores[event]
        elif occasion_scores:
            score = sum(occasion_scores.values()) / len(occasion_scores)
        else:
            score = 0.0
        logger.debug(
            f"[Scoring] '{product.get('name')}' | legacy fallback → score={score:.4f}"
        )
        return score

    # ── New multi-facet scoring ───────────────────────────────────────────────
    total: float = 0.0
    for facet, weight in FACET_WEIGHTS.items():
        user_value: str | None = context.get(facet)
        if user_value is None:
            logger.debug(
                f"[Scoring] '{product.get('name')}' | facet='{facet}' → no user value, skipped"
            )
            continue
        facet_tags: list[dict[str, Any]] = product_tags.get(facet, [])
        table: dict[str, dict[str, float]] = tables.get(facet, {})
        match: float = compute_match(user_value, facet_tags, table)
        contribution: float = weight * match
        total += contribution
        logger.debug(
            f"[Scoring] '{product.get('name')}' | facet='{facet}' "
            f"weight={weight} × match={match:.4f} = {contribution:.4f}"
        )
    logger.debug(f"[Scoring] '{product.get('name')}' → total score={total:.4f}")
    return total


def apply_hard_filters(
    products: list[dict[str, Any]], budget_max: float
) -> list[dict[str, Any]]:
    """
    Pure Python hard-filter pass (mirrors the MongoDB query in the repository).
    Useful for unit-testing filtering logic against in-memory data.
    """
    filtered = [
        p for p in products
        if p.get("price", float("inf")) <= budget_max
        and p.get("stock", 0) > 0
        and p.get("status") == "active"
    ]
    logger.debug(
        f"[apply_hard_filters] {len(products)} in → {len(filtered)} out "
        f"(budget_max={budget_max})"
    )
    return filtered


def rank_products(
    products: list[dict[str, Any]],
    context: QueryContext,
    tables: dict[str, dict[str, dict[str, float]]],
) -> list[dict[str, Any]]:
    """Score and sort a list of products descending by computed score."""
    scored = [
        {**p, "_score": compute_score(p, context, tables), "_explanation": build_explanation(p, context, tables)}
        for p in products
    ]
    scored.sort(key=lambda p: p["_score"], reverse=True)
    logger.debug(f"[rank_products] Ranked {len(scored)} products.")
    return scored


def get_recommendations(query: str, budget_max: float) -> list[dict[str, Any]]:
    """
    Full recommendation pipeline:
      1. Interpret query → extract QueryContext (event, relationship, theme, recipient_gender)
      2. Load similarity tables (cached)
      3. Fetch candidate products (hard filters applied in repository via MongoDB query)
      4. Rank by multi-facet score
      5. Return top N
    """
    db = get_db()
    collection_name = os.getenv("PRODUCTS_COLLECTION", "products")

    context = interpret_query(query)
    tables = load_all_similarity_tables()
    logger.debug(f"[Service] Query interpreted → context={context}")

    products = fetch_candidate_products(db, budget_max, collection_name=collection_name)
    logger.debug(f"[Service] {len(products)} products after hard filtering (collection='{collection_name}').")

    top = rank_products(products, context, tables)[:TOP_N]

    logger.debug(f"[Service] Returning top {len(top)} recommendations (TOP_N={TOP_N}).")
    return top
