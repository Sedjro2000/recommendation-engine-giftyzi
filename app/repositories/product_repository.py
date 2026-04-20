import logging
from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo.database import Database

logger = logging.getLogger(__name__)


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


def fetch_candidate_products(
    db: Database,
    budget_max: float,
    collection_name: str = "products",
) -> list[dict[str, Any]]:
    """
    Fetch products from MongoDB applying hard filters:
      - price  <= budget_max
      - stock  >  0
      - status == "active"

    The _id field is excluded from results.
    Pass collection_name to target a non-default collection (e.g. in tests).
    """
    collection = db[collection_name]

    mongo_filter = {
        "price": {"$lte": budget_max},
        "stock": {"$gt": 0},
        "status": "active",
    }

    raw = collection.find(mongo_filter, {"_id": 0})
    products = [_bson_to_json(doc) for doc in raw]
    logger.debug(f"[Repository] Hard filters applied → {len(products)} products retrieved.")
    return products
