import logging
import os
from typing import Any

from app.db.client import get_db
from app.repositories.product_repository import fetch_candidate_products
from app.services.query_interpreter import interpret_query

logger = logging.getLogger(__name__)

TOP_N = 10


def _compute_score(product: dict[str, Any], occasions: list[str]) -> float:
    """
    Score a product using its occasion_score map.

    - If specific occasions were detected, return the max score for those occasions.
    - If no occasion was detected (or the product has no matching keys),
      fall back to the average of all defined occasion scores.
    - Returns 0.0 if the field is absent or empty.
    """
    occasion_scores: dict[str, float] = product.get("occasion_score", {})

    if not occasion_scores:
        logger.debug(f"[Scoring] '{product.get('name')}' → no occasion_score field, score=0.0")
        return 0.0

    if occasions:
        matched = [occasion_scores[occ] for occ in occasions if occ in occasion_scores]
        if matched:
            score = max(matched)
            logger.debug(
                f"[Scoring] '{product.get('name')}' | occasions={occasions} "
                f"→ matched scores={matched}, score={score:.4f}"
            )
            return score

    score = sum(occasion_scores.values()) / len(occasion_scores)
    logger.debug(
        f"[Scoring] '{product.get('name')}' | no occasion match "
        f"→ avg fallback score={score:.4f}"
    )
    return score


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
    products: list[dict[str, Any]], occasions: list[str]
) -> list[dict[str, Any]]:
    """Score and sort a list of products descending by computed score."""
    scored = [{**p, "_score": _compute_score(p, occasions)} for p in products]
    scored.sort(key=lambda p: p["_score"], reverse=True)
    logger.debug(f"[rank_products] Ranked {len(scored)} products.")
    return scored


def get_recommendations(query: str, budget_max: float) -> list[dict[str, Any]]:
    """
    Full recommendation pipeline:
      1. Interpret query → extract occasions
      2. Fetch candidate products (hard filters applied in repository via MongoDB query)
      3. Rank by score
      4. Return top N
    """
    db = get_db()
    collection_name = os.getenv("PRODUCTS_COLLECTION", "products")

    occasions = interpret_query(query)
    logger.debug(f"[Service] Query interpreted → occasions={occasions}")

    products = fetch_candidate_products(db, budget_max, collection_name=collection_name)
    logger.debug(f"[Service] {len(products)} products after hard filtering (collection='{collection_name}').")

    top = rank_products(products, occasions)[:TOP_N]

    logger.debug(f"[Service] Returning top {len(top)} recommendations (TOP_N={TOP_N}).")
    return top
