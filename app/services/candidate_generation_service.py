import logging
import os
from typing import Any

from app.core.architecture_guard import assert_service_call_allowed
from app.db.client import get_db
from app.repositories.product_repository import fetch_candidate_products
from app.schemas.recommendation import RecommendationRequest

logger = logging.getLogger(__name__)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _matches_hard_filters(product: dict[str, Any], hard_filters: dict[str, Any] | None) -> bool:
    if not hard_filters:
        return True

    for field, requested in hard_filters.items():
        requested_values = _as_list(requested)
        if not requested_values:
            continue

        product_values = _as_list(product.get(field))
        if not set(requested_values) & set(product_values):
            return False
    return True


def candidate_generation_service(
    request: RecommendationRequest,
    query_understanding: dict[str, Any],
) -> dict[str, Any]:
    assert_service_call_allowed("candidate_generation")
    del query_understanding

    db = get_db()
    collection_name = os.getenv(
        "PRODUCTS_COLLECTION",
        "ProductRecommendationProjection",
    )
    products = fetch_candidate_products(
        db,
        budget_max=request.budget_max,
        collection_name=collection_name,
    )
    filtered_products = [
        product
        for product in products
        if product.get("stock", 0) > 0
        and _matches_hard_filters(product, request.hard_filters)
    ]

    logger.debug(
        "[candidate_generation] %s candidates after stock/budget/hard filters.",
        len(filtered_products),
    )
    return {
        "_candidates": filtered_products,
        "total_candidates": len(filtered_products),
        "filters_applied": {
            "stock": "stock > 0",
            "budget_max": request.budget_max,
            "hard_filters": request.hard_filters or {},
        },
    }
