from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services import recommendation_service


PUBLIC_RESPONSE_KEYS = {
    "query_interpretation",
    "hard_constraints",
    "soft_preferences",
    "best_matches",
    "explanation",
    "related_ideas",
    "relaxations_applied",
    "suggested_reformulations",
    "fallback",
    "meta",
    "debug_info",
}

BEST_MATCH_REQUIRED_KEYS = {
    "_id",
    "product_id",
    "name",
    "price",
    "stock",
    "status",
    "age_group",
    "recipient_gender",
    "tags",
    "_score",
    "_explanation",
}


def _stub_ranked_products(
    monkeypatch: pytest.MonkeyPatch,
    products: list[dict[str, Any]],
) -> None:
    monkeypatch.setattr(
        recommendation_service,
        "get_recommendations",
        lambda request: products,
    )


def _assert_public_response_contract(body: dict[str, Any]) -> None:
    assert set(body) == PUBLIC_RESPONSE_KEYS
    assert isinstance(body["query_interpretation"], dict)
    assert isinstance(body["hard_constraints"], dict)
    assert isinstance(body["soft_preferences"], dict)
    assert isinstance(body["best_matches"], list)
    assert isinstance(body["explanation"], dict)
    assert isinstance(body["related_ideas"], list)
    assert isinstance(body["relaxations_applied"], list)
    assert isinstance(body["suggested_reformulations"], list)
    assert body["fallback"] is None or isinstance(body["fallback"], dict)
    assert isinstance(body["meta"], dict)
    assert isinstance(body["debug_info"], dict)

    assert set(body["meta"]) == {"result_count", "limit", "contract_version"}
    assert body["meta"]["contract_version"] == "recommendation_public_v1"
    assert body["meta"]["limit"] == 10
    assert body["meta"]["result_count"] == len(body["best_matches"])

    assert set(body["debug_info"]) == {
        "scoring_formula",
        "stock_filter",
        "exact_match_score",
        "suggestion_builder_enabled",
        "phase",
    }
    assert body["debug_info"]["stock_filter"] == "stock > 0"
    assert body["debug_info"]["exact_match_score"] == 1.0
    assert body["debug_info"]["phase"] == "8bis"


def test_valid_nextjs_payload_is_parsed_and_returns_contract(
    api_client: TestClient,
    nextjs_recommendation_payload: dict[str, Any],
    mock_ranked_products: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_ranked_products(monkeypatch, mock_ranked_products)

    response = api_client.post("/api/v1/recommend", json=nextjs_recommendation_payload)

    assert response.status_code == 200
    body = response.json()
    _assert_public_response_contract(body)

    assert body["hard_constraints"] == {
        "status": "active",
        "budget_max": 80.0,
        "availability": "in_stock",
        "recipient_gender": ["female"],
        "age_group": ["adulte"],
    }
    assert body["soft_preferences"] == {
        "event": ["anniversaire"],
        "relationship": ["partenaire"],
        "theme": ["romantic"],
        "gift_benefit": ["emotional"],
        "facet_weights": {
            "event": 1.3,
            "relationship": 1.1,
            "theme": 0.9,
            "gift_benefit": 1.0,
        },
    }
    assert body["query_interpretation"]["detected_signals"] == {
        "budget_max": 80.0,
        "event": ["anniversaire"],
        "relationship": ["partenaire"],
        "theme": ["romantic"],
        "gift_benefit": ["emotional"],
        "recipient_gender": ["female"],
        "age_group": ["adulte"],
    }

    match = body["best_matches"][0]
    assert BEST_MATCH_REQUIRED_KEYS.issubset(match)
    assert isinstance(match["product_id"], str)
    assert isinstance(match["_score"], float)
    assert set(match["_explanation"]) == {
        "matched_hard_filters",
        "matched_soft_tags",
        "score_breakdown",
    }
    assert match["_explanation"]["score_breakdown"]["total_score"] == match["_score"]


def test_camel_case_payload_is_rejected(
    api_client: TestClient,
    nextjs_recommendation_payload: dict[str, Any],
) -> None:
    payload = {
        "status": "active",
        "budgetMax": nextjs_recommendation_payload["budget_max"],
        "hardFilters": {
            "recipientGender": ["female"],
            "ageGroup": ["adulte"],
        },
        "softTags": {
            "giftBenefit": [{"slug": "emotional", "intensity": 1.0}],
            "theme": [{"slug": "romantic", "intensity": 1.0}],
        },
        "facetWeights": {"theme": 0.9, "giftBenefit": 1.0},
    }

    response = api_client.post("/api/v1/recommend", json=payload)

    assert response.status_code == 422
    error_locations = {tuple(error["loc"]) for error in response.json()["detail"]}
    assert ("body", "budgetMax") in error_locations
    assert ("body", "hardFilters") in error_locations
    assert ("body", "softTags") in error_locations
    assert ("body", "facetWeights") in error_locations


def test_missing_required_field_is_rejected(
    api_client: TestClient,
    nextjs_recommendation_payload: dict[str, Any],
) -> None:
    payload = {
        key: value
        for key, value in nextjs_recommendation_payload.items()
        if key != "status"
    }

    response = api_client.post("/api/v1/recommend", json=payload)

    assert response.status_code == 422
    assert ("body", "status") in {
        tuple(error["loc"]) for error in response.json()["detail"]
    }


def test_budget_max_string_is_rejected(
    api_client: TestClient,
    nextjs_recommendation_payload: dict[str, Any],
) -> None:
    payload = {**nextjs_recommendation_payload, "budget_max": "80.0"}

    response = api_client.post("/api/v1/recommend", json=payload)

    assert response.status_code == 422
    assert ("body", "budget_max") in {
        tuple(error["loc"]) for error in response.json()["detail"]
    }


@pytest.mark.parametrize(
    "payload_update",
    [
        {"soft_tags": {"theme": [{"slug": "unknown-theme", "intensity": 1.0}]}},
        {
            "soft_tags": {
                "gift_benefit": [{"slug": "unknown-benefit", "intensity": 1.0}]
            }
        },
    ],
)
def test_unknown_soft_tag_slug_is_rejected(
    api_client: TestClient,
    nextjs_recommendation_payload: dict[str, Any],
    payload_update: dict[str, Any],
) -> None:
    payload = {**nextjs_recommendation_payload, **payload_update}

    response = api_client.post("/api/v1/recommend", json=payload)

    assert response.status_code == 422
    assert "unknown slug" in response.text


def test_empty_payload_is_rejected(api_client: TestClient) -> None:
    response = api_client.post("/api/v1/recommend", json={})

    assert response.status_code == 422
    assert ("body", "status") in {
        tuple(error["loc"]) for error in response.json()["detail"]
    }


def test_no_recommendations_returns_stable_empty_response(
    api_client: TestClient,
    nextjs_recommendation_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_ranked_products(monkeypatch, [])

    response = api_client.post("/api/v1/recommend", json=nextjs_recommendation_payload)

    assert response.status_code == 200
    body = response.json()
    _assert_public_response_contract(body)
    assert body["best_matches"] == []
    assert body["fallback"] == {
        "reason": "no_matches",
        "message": "Aucun produit ne correspond aux contraintes actuelles.",
    }
    assert body["meta"]["result_count"] == 0
