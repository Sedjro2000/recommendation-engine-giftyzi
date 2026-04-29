from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api import routes

TEST_COLLECTION = "products_test"
PROJECTION_COLLECTION = "ProductRecommendationProjection"


def test_recommend_endpoint_real_db_returns_ranked_gift_suggestions(
    inserted_products: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", TEST_COLLECTION)

    from app.main import app

    payload = {
        "status": "active",
        "budget_max": 100.0,
        "hard_filters": {
            "age_group": ["adulte"],
            "recipient_gender": ["female", "unisex"],
        },
        "soft_tags": {
            "event": [{"slug": "anniversaire", "intensity": 1.0}],
            "relationship": [{"slug": "partenaire", "intensity": 1.0}],
            "theme": [{"slug": "romantic", "intensity": 1.0}],
            "gift_benefit": [{"slug": "emotional", "intensity": 1.0}],
        },
        "facet_weights": {
            "event": 1.0,
            "relationship": 1.0,
            "theme": 1.0,
            "gift_benefit": 1.0,
        },
    }

    with TestClient(app) as client:
        response = client.post("/api/v1/recommend", json=payload)

    assert response.status_code == 200
    body = response.json()
    matches = body["best_matches"]

    assert body["fallback"] is None
    assert body["meta"]["result_count"] == 3
    assert [match["name"] for match in matches] == [
        "T_Bijou anniversaire",
        "T_Carnet voyage",
        "T_Bougie deco",
    ]
    assert [match["_score"] for match in matches] == sorted(
        [match["_score"] for match in matches],
        reverse=True,
    )
    assert matches[0]["_score"] == pytest.approx(3.6)
    assert matches[1]["_score"] == pytest.approx(0.64)
    assert matches[2]["_score"] == pytest.approx(0.49)

    assert all(match["status"] == "active" for match in matches)
    assert all(match["stock"] > 0 for match in matches)
    assert all(match["price"] <= payload["budget_max"] for match in matches)
    assert not any(match["name"] == "T_Montre luxe" for match in matches)
    assert not any(match["name"] == "T_Parfum epuise" for match in matches)
    assert not any(match["name"] == "T_Agenda inactif" for match in matches)

    top_match = matches[0]
    assert top_match["name"] == "T_Bijou anniversaire"
    assert top_match["_explanation"]["matched_hard_filters"] == {
        "recipient_gender": ["female", "unisex"],
        "age_group": ["adulte"],
    }
    assert top_match["_explanation"]["matched_soft_tags"]["event"][
        "exact_matches"
    ] == ["anniversaire"]
    assert top_match["_explanation"]["matched_soft_tags"]["relationship"][
        "exact_matches"
    ] == ["partenaire"]
    assert top_match["_explanation"]["matched_soft_tags"]["theme"][
        "exact_matches"
    ] == ["romantic"]
    assert top_match["_explanation"]["matched_soft_tags"]["gift_benefit"][
        "exact_matches"
    ] == ["emotional"]

    assert body["soft_preferences"] == {
        "event": ["anniversaire"],
        "relationship": ["partenaire"],
        "theme": ["romantic"],
        "gift_benefit": ["emotional"],
        "facet_weights": {
            "event": 1.0,
            "relationship": 1.0,
            "theme": 1.0,
            "gift_benefit": 1.0,
        },
    }


def test_recommend_endpoint_real_projection_returns_tagged_suggestion(
    test_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", PROJECTION_COLLECTION)

    from app.main import app

    test_product_id = "e2e-projection-tagged-product"

    try:
        test_db[PROJECTION_COLLECTION].insert_one(
            {
                "_id": test_product_id,
                "name": "E2E Recommendation Tagged Product",
                "price": 1.0,
                "stock": 3,
                "status": "active",
                "hard_filters": {
                    "age_group": ["adulte"],
                    "recipient_gender": ["unisex"],
                },
                "soft_tags": {
                    "event": [{"slug": "anniversaire", "intensity": 1.0}],
                    "relationship": [{"slug": "ami", "intensity": 1.0}],
                    "theme": [{"slug": "tech", "intensity": 1.0}],
                    "gift_benefit": [{"slug": "useful", "intensity": 1.0}],
                },
                "facet_weights": {},
            }
        )

        payload = {
            "status": "active",
            "budget_max": 1.0,
            "hard_filters": {
                "age_group": ["adulte"],
                "recipient_gender": ["male", "unisex"],
            },
            "soft_tags": {
                "event": [{"slug": "anniversaire", "intensity": 1.0}],
                "relationship": [{"slug": "ami", "intensity": 1.0}],
                "theme": [{"slug": "tech", "intensity": 1.0}],
                "gift_benefit": [{"slug": "useful", "intensity": 1.0}],
            },
            "facet_weights": {
                "event": 1.0,
                "relationship": 1.0,
                "theme": 1.0,
                "gift_benefit": 1.0,
            },
        }

        with TestClient(app) as client:
            response = client.post("/api/v1/recommend", json=payload)

        assert response.status_code == 200
        body = response.json()
        matches = body["best_matches"]

        assert body["fallback"] is None
        assert len(matches) >= 1

        inserted_match = next(
            match for match in matches if match["_id"] == test_product_id
        )
        assert inserted_match["name"] == "E2E Recommendation Tagged Product"
        assert inserted_match["age_group"] == ["adulte"]
        assert inserted_match["recipient_gender"] == ["unisex"]
        assert inserted_match["_score"] == pytest.approx(4.0)
        assert inserted_match["_explanation"]["matched_hard_filters"] == {
            "recipient_gender": ["unisex"],
            "age_group": ["adulte"],
        }
        assert inserted_match["_explanation"]["matched_soft_tags"]["theme"][
            "exact_matches"
        ] == ["tech"]
        assert inserted_match["_explanation"]["matched_soft_tags"]["gift_benefit"][
            "exact_matches"
        ] == ["useful"]
    finally:
        test_db[PROJECTION_COLLECTION].delete_one({"_id": test_product_id})


def test_recommend_endpoint_maps_controlled_internal_error_to_500(
    api_client: TestClient,
    nextjs_recommendation_payload: dict[str, Any],
    monkeypatch,
) -> None:
    def raise_internal_error(request):
        raise RuntimeError("controlled test failure")

    monkeypatch.setattr(routes, "build_recommendation_response", raise_internal_error)

    response = api_client.post("/api/v1/recommend", json=nextjs_recommendation_payload)

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal recommendation error."}
