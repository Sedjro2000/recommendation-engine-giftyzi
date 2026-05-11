import logging
from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo.database import Database

from app.config.facets import SIMILARITY_FACETS

logger = logging.getLogger(__name__)

SOFT_TAG_FACETS = frozenset(SIMILARITY_FACETS)


def _bson_to_json(doc: dict[str, Any]) -> dict[str, Any]:
    """Recursively convert BSON-specific types to JSON-serializable equivalents."""
    result: dict[str, Any] = {}
    for k, v in doc.items():
        if isinstance(v, ObjectId):
            result[k] = str(v)
        elif isinstance(v, datetime):
            result[k] = v.isoformat()
        elif isinstance(v, dict):
            result[k] = _bson_to_json(v)
        elif isinstance(v, list):
            result[k] = [_bson_to_json(i) if isinstance(i, dict) else (str(i) if isinstance(i, ObjectId) else i) for i in v]
        else:
            result[k] = v
    return result


def _normalize_projection_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """Expose recommendation projection fields in the shape used by the engine."""
    hard_filters = doc.get("hard_filters", {})
    soft_tags = doc.get("soft_tags", {})

    normalized = {
        **doc,
        "age_group": hard_filters.get("age_group", []),
        "recipient_gender": hard_filters.get("recipient_gender", []),
        "tags": {
            facet: soft_tags.get(facet, [])
            for facet in SOFT_TAG_FACETS
        },
    }
    return normalized


def fetch_candidate_products(
    db: Database,
    budget_max: float | None,
    collection_name: str = "products",
) -> list[dict[str, Any]]:
    """
    Fetch products from MongoDB applying DB-level hard filters:
      - price  <= budget_max   (only when request.budget_max is provided)
      - stock  >  0            (Decision #7: stock=0 => always excluded, not overridable)

    The _id field is excluded from results.
    Pass collection_name to target a non-default collection (e.g. in tests).
    """
    logger.info("[Repository] Using collection=%s", collection_name)
    collection = db[collection_name]

    mongo_filter: dict[str, Any] = {
        "stock": {"$gt": 0},
    }
    if budget_max is not None:
        mongo_filter["price"] = {"$lte": budget_max}

    raw = collection.find(mongo_filter)
    raw_products = list(raw)
    if collection_name == "ProductRecommendationProjection":
        raw_products = [_normalize_projection_doc(doc) for doc in raw_products]

    products = [_bson_to_json(doc) for doc in raw_products]
    logger.debug(
        f"[Repository] Hard filters applied → {len(products)} products retrieved "
        f"(budget_max={budget_max})."
    )
    return products
