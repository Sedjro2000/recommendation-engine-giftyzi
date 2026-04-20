"""
GIFTYZI — Integration test suite.

All tests run against the REAL MongoDB instance (Atlas).
Collection used: products_test (never touches products).
"""

import logging

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.database import Database

from app.repositories.product_repository import fetch_candidate_products
from app.services.recommendation_service import apply_hard_filters, rank_products

logger = logging.getLogger(__name__)

TEST_COLLECTION = "products_test"
BUDGET_MAX = 100.0
OCCASIONS = ["anniversaire"]


# ─────────────────────────────────────────────────────────────
# 1. DB CONNECTION
# ─────────────────────────────────────────────────────────────


def test_db_connection(mongo_client: MongoClient) -> None:
    """Verify MongoDB is reachable and ping succeeds."""
    result = mongo_client.admin.command("ping")
    assert result.get("ok") == 1.0, f"Unexpected ping response: {result}"
    logger.debug("[test_db_connection] ping returned ok=1.0 ✓")


# ─────────────────────────────────────────────────────────────
# 2. INSERT & READ
# ─────────────────────────────────────────────────────────────


def test_insert_and_read_products(
    test_db: Database, inserted_products: list[dict]
) -> None:
    """Confirm all 6 test documents were inserted and can be read back."""
    count = test_db[TEST_COLLECTION].count_documents({})
    assert count == 6, f"Expected 6 documents in '{TEST_COLLECTION}', found {count}."

    names = {p["name"] for p in inserted_products}
    expected = {
        "T_Bijou anniversaire",
        "T_Carnet voyage",
        "T_Parfum epuise",
        "T_Montre luxe",
        "T_Agenda inactif",
        "T_Bougie deco",
    }
    assert names == expected, f"Document names mismatch: {names}"
    logger.debug(f"[test_insert_and_read_products] {count} docs verified ✓")


# ─────────────────────────────────────────────────────────────
# 3. HARD FILTERS (Python-level: apply_hard_filters)
# ─────────────────────────────────────────────────────────────


def test_hard_filters(inserted_products: list[dict]) -> None:
    """
    apply_hard_filters() must exclude:
      - stock = 0          (T_Parfum epuise)
      - price > budget     (T_Montre luxe, price=200)
      - status == inactive (T_Agenda inactif)
    And include the 3 remaining valid products.
    """
    filtered = apply_hard_filters(inserted_products, budget_max=BUDGET_MAX)
    filtered_names = {p["name"] for p in filtered}

    # Must be EXCLUDED
    assert "T_Parfum epuise" not in filtered_names, (
        "Product with stock=0 must be excluded."
    )
    assert "T_Montre luxe" not in filtered_names, (
        "Product with price > budget must be excluded."
    )
    assert "T_Agenda inactif" not in filtered_names, (
        "Inactive product must be excluded."
    )

    # Must be INCLUDED
    assert "T_Bijou anniversaire" in filtered_names
    assert "T_Carnet voyage" in filtered_names
    assert "T_Bougie deco" in filtered_names

    assert len(filtered) == 3, f"Expected 3 products after filtering, got {len(filtered)}."
    logger.debug(
        f"[test_hard_filters] {len(filtered)}/6 products passed hard filters ✓"
    )


# ─────────────────────────────────────────────────────────────
# 4. SCORING (rank_products)
# ─────────────────────────────────────────────────────────────


def test_scoring(test_db: Database, inserted_products: list[dict]) -> None:
    """
    rank_products() must place T_Bijou anniversaire (score=0.95) first
    and maintain descending order throughout.
    """
    valid = fetch_candidate_products(
        test_db, budget_max=BUDGET_MAX, collection_name=TEST_COLLECTION
    )
    assert len(valid) > 0, "No products returned by fetch_candidate_products."

    ranked = rank_products(valid, OCCASIONS)
    assert len(ranked) == len(valid), "rank_products must return all input products."

    scores = [p["_score"] for p in ranked]
    assert scores == sorted(scores, reverse=True), (
        "Products are not sorted in descending score order."
    )
    assert ranked[0]["name"] == "T_Bijou anniversaire", (
        f"Expected 'T_Bijou anniversaire' at rank 1, got '{ranked[0]['name']}'."
    )
    assert ranked[0]["_score"] == pytest.approx(0.95), (
        f"Expected score 0.95, got {ranked[0]['_score']}."
    )
    logger.debug(
        f"[test_scoring] Top product: '{ranked[0]['name']}' score={ranked[0]['_score']:.4f} ✓"
    )


# ─────────────────────────────────────────────────────────────
# 5. END-TO-END API ENDPOINT
# ─────────────────────────────────────────────────────────────


def test_recommend_endpoint(inserted_products: list[dict], monkeypatch: pytest.MonkeyPatch) -> None:
    """
    POST /api/v1/recommend must:
      - Return HTTP 200
      - Return a 'best_matches' list with <= 10 items
      - Only include products that satisfy ALL hard constraints
    The env var PRODUCTS_COLLECTION is patched so the API reads from products_test.
    """
    monkeypatch.setenv("PRODUCTS_COLLECTION", TEST_COLLECTION)

    from app.main import app

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/recommend",
            json={"query": "cadeau anniversaire", "budget_max": BUDGET_MAX},
        )

    assert response.status_code == 200, (
        f"Expected HTTP 200, got {response.status_code}. Body: {response.text}"
    )

    body = response.json()
    assert "best_matches" in body, f"'best_matches' key missing from response: {body}"

    matches = body["best_matches"]
    assert isinstance(matches, list), "'best_matches' must be a list."
    assert len(matches) <= 10, f"Expected at most 10 results, got {len(matches)}."
    assert len(matches) == 3, (
        f"Expected exactly 3 products to pass hard filters, got {len(matches)}."
    )

    for product in matches:
        name = product.get("name", "unknown")
        assert product.get("stock", 0) > 0, (
            f"'{name}': stock=0 violates hard filter."
        )
        assert product.get("status") == "active", (
            f"'{name}': status != 'active' violates hard filter."
        )
        assert product.get("price", 0) <= BUDGET_MAX, (
            f"'{name}': price {product.get('price')} > budget {BUDGET_MAX}."
        )

    assert matches[0]["name"] == "T_Bijou anniversaire", (
        f"Expected highest-scored product first, got '{matches[0]['name']}'."
    )

    logger.debug(
        f"[test_recommend_endpoint] {len(matches)} matches returned, "
        f"all hard constraints respected ✓"
    )
