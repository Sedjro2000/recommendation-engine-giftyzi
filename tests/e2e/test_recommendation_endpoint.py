import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

TEST_COLLECTION = "products_test"
PROJECTION_COLLECTION = "ProductRecommendationProjection"


def _full_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "query": "cadeau anniversaire romantique",
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
        "limit": 24,
        "offset": 0,
    }
    payload.update(overrides)
    return payload


def _print_json(label: str, data: Any) -> None:
    print(f"\n{label}")
    print(json.dumps(data, indent=2, ensure_ascii=False))


def test_recommend_endpoint_memory_db_returns_real_v1_response(
    api_client: TestClient,
    inserted_products: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", TEST_COLLECTION)

    response = api_client.post("/api/v1/recommend", json=_full_payload())

    assert response.status_code == 200
    body = response.json()
    _print_json("REAL_V1_FULL_RESPONSE", body)

    assert set(body) == {
        "query_understanding",
        "suggested_reformulations",
        "candidate_generation",
        "best_matches",
        "similarity_ideas",
        "related_ideas",
        "meta",
    }
    assert body["query_understanding"]["missing_signals"] == ["gift_type"]
    assert body["suggested_reformulations"] == []
    assert body["related_ideas"] == []
    assert body["candidate_generation"]["total_candidates"] == 4

    matches = body["best_matches"]
    assert [match["name"] for match in matches] == [
        "T_Bijou anniversaire",
        "T_Agenda inactif",
        "T_Carnet voyage",
        "T_Bougie deco",
    ]
    assert [match["score"] for match in matches] == sorted(
        [match["score"] for match in matches],
        reverse=True,
    )
    assert all("_score" not in match for match in matches)
    assert all(0.0 <= match["score"] <= 1.0 for match in matches)
    assert all(match["stock"] > 0 for match in matches)
    assert all(match["price"] <= 100.0 for match in matches)
    assert not any(match["name"] == "T_Parfum epuise" for match in matches)
    assert not any(match["name"] == "T_Montre luxe" for match in matches)

    assert body["similarity_ideas"]
    assert all(
        set(idea) == {
            "product_id",
            "source_product_id",
            "similarity_score",
            "reason",
        }
        for idea in body["similarity_ideas"]
    )
    assert all(
        0.0 <= idea["similarity_score"] <= 1.0
        for idea in body["similarity_ideas"]
    )


def test_recommend_endpoint_memory_db_returns_guidance_when_query_is_sparse(
    api_client: TestClient,
    inserted_products: list[dict[str, Any]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", TEST_COLLECTION)

    payload = {
        "query": "cadeau",
        "budget_max": 40.0,
        "hard_filters": {"age_group": ["adulte"]},
        "limit": 24,
        "offset": 0,
    }
    response = api_client.post("/api/v1/recommend", json=payload)

    assert response.status_code == 200
    body = response.json()
    _print_json("REAL_V1_SPARSE_QUERY_RESPONSE", body)

    assert body["query_understanding"]["missing_signals"] == [
        "event",
        "relationship",
        "theme",
        "gift_benefit",
        "gift_type",
    ]
    assert body["suggested_reformulations"] == [
        {
            "label": "Preciser l'occasion",
            "reason": "L'occasion manque pour guider la recherche.",
            "source": "missing_signal",
        },
        {
            "label": "Preciser le lien",
            "reason": "Le lien avec la personne manque pour guider la recherche.",
            "source": "missing_signal",
        },
        {
            "label": "Preciser le theme",
            "reason": "Le theme manque pour guider la recherche.",
            "source": "missing_signal",
        },
    ]
    assert body["related_ideas"] == [
        {
            "idea_id": "explore-event",
            "title": "Explorer par occasion",
            "reason": "Une occasion peut ouvrir des pistes cadeau plus ciblees.",
            "soft_tags": {"event": ["TODO"]},
        },
        {
            "idea_id": "explore-relationship",
            "title": "Explorer par relation",
            "reason": "La relation peut aider a varier les pistes cadeau.",
            "soft_tags": {"relationship": ["TODO"]},
        },
    ]
    assert all("product_id" not in idea for idea in body["related_ideas"])
    assert all("score" not in idea for idea in body["related_ideas"])
    assert body["best_matches"]


def test_recommend_endpoint_memory_projection_returns_tagged_suggestion(
    api_client: TestClient,
    test_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", PROJECTION_COLLECTION)
    test_product_id = "e2e-projection-tagged-product"

    test_db[PROJECTION_COLLECTION].insert_one(
        {
            "_id": test_product_id,
            "name": "E2E Recommendation Tagged Product",
            "price": 1.0,
            "stock": 3,
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
        }
    )

    payload = _full_payload(
        budget_max=1.0,
        hard_filters={
            "age_group": ["adulte"],
            "recipient_gender": ["male", "unisex"],
        },
        soft_tags={
            "event": [{"slug": "anniversaire", "intensity": 1.0}],
            "relationship": [{"slug": "ami", "intensity": 1.0}],
            "theme": [{"slug": "tech", "intensity": 1.0}],
            "gift_benefit": [{"slug": "useful", "intensity": 1.0}],
        },
    )
    response = api_client.post("/api/v1/recommend", json=payload)

    assert response.status_code == 200
    body = response.json()
    _print_json("REAL_V1_PROJECTION_RESPONSE", body)

    matches = body["best_matches"]
    assert len(matches) == 1
    assert matches[0]["_id"] == test_product_id
    assert matches[0]["name"] == "E2E Recommendation Tagged Product"
    assert matches[0]["age_group"] == ["adulte"]
    assert matches[0]["recipient_gender"] == ["unisex"]
    assert matches[0]["score"] == pytest.approx(1.0)
    assert "_score" not in matches[0]


def test_recommend_endpoint_projection_gift_type_boosts_matching_product(
    api_client: TestClient,
    test_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", PROJECTION_COLLECTION)
    test_db[PROJECTION_COLLECTION].drop()
    test_db[PROJECTION_COLLECTION].insert_many(
        [
            {
                "_id": "projection-gift-type-a",
                "name": "Projection Coffret",
                "price": 30.0,
                "stock": 5,
                "hard_filters": {
                    "age_group": ["adulte"],
                    "recipient_gender": ["unisex"],
                },
                "soft_tags": {
                    "event": [{"slug": "anniversaire", "intensity": 1.0}],
                    "gift_type": [{"slug": "coffret", "intensity": 1.0}],
                },
            },
            {
                "_id": "projection-gift-type-b",
                "name": "Projection Sans Gift Type",
                "price": 30.0,
                "stock": 5,
                "hard_filters": {
                    "age_group": ["adulte"],
                    "recipient_gender": ["unisex"],
                },
                "soft_tags": {
                    "event": [{"slug": "anniversaire", "intensity": 1.0}],
                },
            },
        ]
    )

    payload = _full_payload(
        budget_max=40.0,
        hard_filters={
            "age_group": ["adulte"],
            "recipient_gender": ["unisex"],
        },
        soft_tags={
            "event": [{"slug": "anniversaire", "intensity": 1.0}],
            "gift_type": [{"slug": "coffret", "intensity": 1.0}],
        },
        facet_weights={
            "event": 1.0,
            "gift_type": 20.0,
        },
    )

    response = api_client.post("/api/v1/recommend", json=payload)

    assert response.status_code == 200
    body = response.json()
    matches = body["best_matches"]
    assert [match["_id"] for match in matches] == [
        "projection-gift-type-a",
        "projection-gift-type-b",
    ]
    assert matches[0]["score"] > matches[1]["score"]
    assert body["query_understanding"]["detected_signals"]["gift_type"] == ["coffret"]


def test_recommend_endpoint_gift_type_remains_soft_when_no_product_matches(
    api_client: TestClient,
    test_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", PROJECTION_COLLECTION)
    test_db[PROJECTION_COLLECTION].drop()
    test_db[PROJECTION_COLLECTION].insert_many(
        [
            {
                "_id": "projection-gift-type-soft-a",
                "name": "Projection Kit",
                "price": 25.0,
                "stock": 4,
                "hard_filters": {
                    "age_group": ["adulte"],
                    "recipient_gender": ["unisex"],
                },
                "soft_tags": {
                    "event": [{"slug": "anniversaire", "intensity": 1.0}],
                    "gift_type": [{"slug": "kit", "intensity": 1.0}],
                },
            },
            {
                "_id": "projection-gift-type-soft-b",
                "name": "Projection Sans Format",
                "price": 19.0,
                "stock": 4,
                "hard_filters": {
                    "age_group": ["adulte"],
                    "recipient_gender": ["unisex"],
                },
                "soft_tags": {
                    "event": [{"slug": "anniversaire", "intensity": 1.0}],
                },
            },
        ]
    )

    payload = _full_payload(
        budget_max=40.0,
        hard_filters={
            "age_group": ["adulte"],
            "recipient_gender": ["unisex"],
        },
        soft_tags={
            "event": [{"slug": "anniversaire", "intensity": 1.0}],
            "gift_type": [{"slug": "coffret", "intensity": 1.0}],
        },
        facet_weights={
            "event": 1.0,
            "gift_type": 20.0,
        },
    )

    response = api_client.post("/api/v1/recommend", json=payload)

    assert response.status_code == 200
    body = response.json()
    matches = body["best_matches"]
    assert [match["_id"] for match in matches] == [
        "projection-gift-type-soft-a",
        "projection-gift-type-soft-b",
    ]
    assert len(matches) == 2
    assert all(match["score"] > 0 for match in matches)


def test_recommend_endpoint_projection_collection_excludes_non_active_statuses(
    api_client: TestClient,
    test_db,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", PROJECTION_COLLECTION)
    test_db[PROJECTION_COLLECTION].drop()
    test_db[PROJECTION_COLLECTION].insert_many(
        [
            {
                "_id": "projection-active",
                "name": "Projection Active",
                "status": "active",
                "price": 20.0,
                "stock": 5,
                "hard_filters": {
                    "age_group": ["adulte"],
                    "recipient_gender": ["unisex"],
                },
                "soft_tags": {
                    "event": [{"slug": "anniversaire", "intensity": 1.0}],
                },
            },
            {
                "_id": "projection-archived",
                "name": "Projection Archived",
                "status": "archived",
                "price": 20.0,
                "stock": 5,
                "hard_filters": {
                    "age_group": ["adulte"],
                    "recipient_gender": ["unisex"],
                },
                "soft_tags": {
                    "event": [{"slug": "anniversaire", "intensity": 1.0}],
                },
            },
            {
                "_id": "projection-inactive",
                "name": "Projection Inactive",
                "status": "inactive",
                "price": 20.0,
                "stock": 5,
                "hard_filters": {
                    "age_group": ["adulte"],
                    "recipient_gender": ["unisex"],
                },
                "soft_tags": {
                    "event": [{"slug": "anniversaire", "intensity": 1.0}],
                },
            },
            {
                "_id": "projection-draft",
                "name": "Projection Draft",
                "status": "draft",
                "price": 20.0,
                "stock": 5,
                "hard_filters": {
                    "age_group": ["adulte"],
                    "recipient_gender": ["unisex"],
                },
                "soft_tags": {
                    "event": [{"slug": "anniversaire", "intensity": 1.0}],
                },
            },
        ]
    )

    response = api_client.post(
        "/api/v1/recommend",
        json=_full_payload(
            budget_max=50.0,
            hard_filters={
                "age_group": ["adulte"],
                "recipient_gender": ["unisex"],
            },
            soft_tags={
                "event": [{"slug": "anniversaire", "intensity": 1.0}],
            },
            facet_weights={
                "event": 1.0,
            },
        ),
    )

    assert response.status_code == 200
    body = response.json()
    matches = body["best_matches"]
    assert [match["_id"] for match in matches] == ["projection-active"]
    assert all(match["status"] == "active" for match in matches)
