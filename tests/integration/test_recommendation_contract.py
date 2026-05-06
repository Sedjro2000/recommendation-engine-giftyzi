from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services import recommendation_service


PUBLIC_RESPONSE_KEYS = {
    "total_candidates",
    "returned_count",
    "limit",
    "offset",
    "has_more",
    "next_offset",
    "query_interpretation",
    "hard_constraints",
    "soft_preferences",
    "best_matches",
    "similarity_ideas",
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
    "score",
    "reason",
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


def _ranked_product(index: int) -> dict[str, Any]:
    return {
        "_id": f"product-{index:03d}",
        "product_id": f"gift-{index:03d}",
        "name": f"Produit {index:03d}",
        "price": 10.0,
        "stock": 5,
        "status": "active",
        "age_group": ["adulte"],
        "recipient_gender": ["unisex"],
        "tags": {},
        "_score": float(200 - index),
        "score": 1.0,
        "reason": "Stubbed ranked product.",
    }


def _ranked_products(count: int) -> list[dict[str, Any]]:
    return [_ranked_product(index) for index in range(count)]


def _assert_public_response_contract(body: dict[str, Any]) -> None:
    assert set(body) == PUBLIC_RESPONSE_KEYS
    assert isinstance(body["total_candidates"], int)
    assert isinstance(body["returned_count"], int)
    assert isinstance(body["limit"], int)
    assert isinstance(body["offset"], int)
    assert isinstance(body["has_more"], bool)
    assert body["next_offset"] is None or isinstance(body["next_offset"], int)
    assert isinstance(body["query_interpretation"], dict)
    assert isinstance(body["hard_constraints"], dict)
    assert isinstance(body["soft_preferences"], dict)
    assert isinstance(body["best_matches"], list)
    assert isinstance(body["similarity_ideas"], list)
    assert isinstance(body["explanation"], dict)
    assert isinstance(body["related_ideas"], list)
    assert isinstance(body["relaxations_applied"], list)
    assert isinstance(body["suggested_reformulations"], list)
    assert body["fallback"] is None or isinstance(body["fallback"], dict)
    assert isinstance(body["meta"], dict)
    assert isinstance(body["debug_info"], dict)

    assert body["returned_count"] == len(body["best_matches"])
    assert body["offset"] >= 0

    assert set(body["meta"]) == {
        "result_count",
        "limit",
        "offset",
        "total_candidates",
        "returned_count",
        "has_more",
        "next_offset",
        "contract_version",
    }
    assert body["meta"]["contract_version"] == "recommendation_public_v1"
    assert body["meta"]["limit"] == body["limit"]
    assert body["meta"]["offset"] == body["offset"]
    assert body["meta"]["total_candidates"] == body["total_candidates"]
    assert body["meta"]["returned_count"] == body["returned_count"]
    assert body["meta"]["has_more"] == body["has_more"]
    assert body["meta"]["next_offset"] == body["next_offset"]
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
    assert body["debug_info"]["suggestion_builder_enabled"] is False
    assert body["debug_info"]["phase"] == "post_refactor_v1"


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
    assert body["explanation"]["missing_signals"] == []
    assert body["suggested_reformulations"] == []

    match = body["best_matches"][0]
    assert BEST_MATCH_REQUIRED_KEYS.issubset(match)
    assert isinstance(match["product_id"], str)
    assert isinstance(match["_score"], float)
    assert isinstance(match["score"], float)
    assert 0.0 <= match["score"] <= 1.0
    assert isinstance(match["reason"], str)
    assert match["reason"]
    assert set(match["_explanation"]) == {
        "matched_hard_filters",
        "matched_soft_tags",
        "score_breakdown",
    }
    assert match["_explanation"]["score_breakdown"]["total_score"] == match["_score"]


def test_default_pagination_uses_env_limit_and_zero_offset(
    api_client: TestClient,
    nextjs_recommendation_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RECOMMENDATION_DEFAULT_LIMIT", "7")
    monkeypatch.setenv("RECOMMENDATION_MAX_LIMIT", "100")
    _stub_ranked_products(monkeypatch, _ranked_products(20))

    response = api_client.post("/api/v1/recommend", json=nextjs_recommendation_payload)

    assert response.status_code == 200
    body = response.json()
    assert body["total_candidates"] == 20
    assert body["returned_count"] == 7
    assert body["limit"] == 7
    assert body["offset"] == 0
    assert body["has_more"] is True
    assert body["next_offset"] == 7
    assert [item["product_id"] for item in body["best_matches"]] == [
        f"gift-{index:03d}" for index in range(7)
    ]


def test_limit_and_offset_return_first_page_metadata(
    api_client: TestClient,
    nextjs_recommendation_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_ranked_products(monkeypatch, _ranked_products(60))
    payload = {**nextjs_recommendation_payload, "limit": 24, "offset": 0}

    response = api_client.post("/api/v1/recommend", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["returned_count"] == 24
    assert body["has_more"] is True
    assert body["next_offset"] == 24
    assert [item["product_id"] for item in body["best_matches"]] == [
        f"gift-{index:03d}" for index in range(24)
    ]


def test_offset_returns_next_page_without_duplicates(
    api_client: TestClient,
    nextjs_recommendation_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ranked = _ranked_products(60)
    _stub_ranked_products(monkeypatch, ranked)
    first_payload = {**nextjs_recommendation_payload, "limit": 24, "offset": 0}
    second_payload = {**nextjs_recommendation_payload, "limit": 24, "offset": 24}

    first = api_client.post("/api/v1/recommend", json=first_payload).json()
    second_response = api_client.post("/api/v1/recommend", json=second_payload)

    assert second_response.status_code == 200
    second = second_response.json()
    assert [item["product_id"] for item in second["best_matches"]] == [
        f"gift-{index:03d}" for index in range(24, 48)
    ]
    assert {
        item["product_id"] for item in first["best_matches"]
    }.isdisjoint({item["product_id"] for item in second["best_matches"]})


def test_offset_near_end_returns_short_final_page(
    api_client: TestClient,
    nextjs_recommendation_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_ranked_products(monkeypatch, _ranked_products(180))
    payload = {**nextjs_recommendation_payload, "limit": 24, "offset": 168}

    response = api_client.post("/api/v1/recommend", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["returned_count"] == 12
    assert body["has_more"] is False
    assert body["next_offset"] is None
    assert [item["product_id"] for item in body["best_matches"]] == [
        f"gift-{index:03d}" for index in range(168, 180)
    ]


def test_limit_above_max_is_clamped(
    api_client: TestClient,
    nextjs_recommendation_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RECOMMENDATION_MAX_LIMIT", "5")
    _stub_ranked_products(monkeypatch, _ranked_products(20))
    payload = {**nextjs_recommendation_payload, "limit": 50, "offset": 0}

    response = api_client.post("/api/v1/recommend", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 5
    assert body["returned_count"] == 5
    assert body["next_offset"] == 5


def test_negative_offset_is_rejected(
    api_client: TestClient,
    nextjs_recommendation_payload: dict[str, Any],
) -> None:
    response = api_client.post(
        "/api/v1/recommend",
        json={**nextjs_recommendation_payload, "offset": -1},
    )

    assert response.status_code == 422
    assert ("body", "offset") in {
        tuple(error["loc"]) for error in response.json()["detail"]
    }


@pytest.mark.parametrize("limit", [0, -1])
def test_non_positive_limit_is_rejected(
    api_client: TestClient,
    nextjs_recommendation_payload: dict[str, Any],
    limit: int,
) -> None:
    response = api_client.post(
        "/api/v1/recommend",
        json={**nextjs_recommendation_payload, "limit": limit},
    )

    assert response.status_code == 422
    assert ("body", "limit") in {
        tuple(error["loc"]) for error in response.json()["detail"]
    }


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
