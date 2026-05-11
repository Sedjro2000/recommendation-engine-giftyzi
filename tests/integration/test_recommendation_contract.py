from typing import Any

from fastapi.testclient import TestClient

from app.config.facets import SOFT_FACET_DEFAULT_WEIGHTS, SOFT_FACET_SLUGS
from app.core.architecture_guard import ArchitectureGuard, ArchitectureGuardError
from app.orchestrator import recommendation_pipeline
from app.schemas.recommendation import RecommendationRequest
from app.services.query_understanding_service import query_understanding_service


PUBLIC_RESPONSE_KEYS = {
    "query_understanding",
    "suggested_reformulations",
    "candidate_generation",
    "best_matches",
    "similarity_ideas",
    "related_ideas",
    "meta",
}

LEGACY_PUBLIC_KEYS = {
    "fallback",
    "debug_info",
    "hard_constraints",
    "soft_preferences",
    "query_interpretation",
    "relaxations_applied",
}


def _payload() -> dict[str, Any]:
    return {
        "query": "cadeau anniversaire romantique",
        "budget_max": 80.0,
        "hard_filters": {
            "recipient_gender": ["female"],
            "age_group": ["adulte"],
        },
        "soft_tags": {
            "event": [{"slug": "anniversaire", "intensity": 1.0}],
            "relationship": [{"slug": "partenaire", "intensity": 1.0}],
            "theme": [{"slug": "romantic", "intensity": 1.0}],
            "gift_benefit": [{"slug": "emotional", "intensity": 1.0}],
            "gift_type": [{"slug": "coffret", "intensity": 1.0}],
        },
        "facet_weights": {
            "event": 1.0,
            "relationship": 1.0,
            "theme": 1.0,
            "gift_benefit": 1.0,
            "gift_type": 20.0,
        },
        "limit": 2,
        "offset": 0,
    }


def _candidate(index: int, *, score_slug: str = "anniversaire") -> dict[str, Any]:
    return {
        "_id": f"product-{index}",
        "product_id": f"gift-{index}",
        "name": f"Produit {index}",
        "price": 20.0,
        "stock": 3,
        "age_group": ["adulte"],
        "recipient_gender": ["female"],
        "tags": {
            "event": [{"slug": score_slug, "intensity": 1.0}],
            "relationship": [{"slug": "partenaire", "intensity": 1.0}],
            "theme": [{"slug": "romantic", "intensity": 1.0}],
            "gift_benefit": [{"slug": "emotional", "intensity": 1.0}],
            "gift_type": [{"slug": "coffret", "intensity": 1.0}],
        },
    }


def test_recommendation_endpoint_returns_strict_v1_contract(
    api_client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        recommendation_pipeline,
        "candidate_generation_service",
        lambda request, query_understanding: {
            "_candidates": [_candidate(1), _candidate(2)],
            "total_candidates": 2,
            "filters_applied": {
                "stock": "stock > 0",
                "budget_max": request.budget_max,
                "hard_filters": request.hard_filters or {},
            },
        },
    )

    response = api_client.post("/api/v1/recommend", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert set(body) == PUBLIC_RESPONSE_KEYS
    assert not LEGACY_PUBLIC_KEYS & set(body)

    assert body["query_understanding"] == {
        "detected_signals": {
            "event": ["anniversaire"],
            "relationship": ["partenaire"],
            "theme": ["romantic"],
            "gift_benefit": ["emotional"],
            "gift_type": ["coffret"],
        },
        "confidence": {},
        "missing_signals": [],
    }
    assert body["suggested_reformulations"] == []
    assert body["candidate_generation"] == {
        "total_candidates": 2,
        "filters_applied": {
            "stock": "stock > 0",
            "budget_max": 80.0,
            "hard_filters": {
                "recipient_gender": ["female"],
                "age_group": ["adulte"],
            },
        },
    }
    assert "_candidates" not in body["candidate_generation"]

    assert len(body["best_matches"]) == 2
    assert body["best_matches"][0]["product_id"] == "gift-1"
    assert "_score" not in body["best_matches"][0]
    assert 0.0 <= body["best_matches"][0]["score"] <= 1.0
    assert body["similarity_ideas"][0] == {
        "product_id": "gift-2",
        "source_product_id": "gift-1",
        "similarity_score": 1.0,
        "reason": "Similarite UX basee uniquement sur les tags produit.",
    }
    assert body["related_ideas"] == []
    assert body["meta"] == {
        "limit": 2,
        "offset": 0,
        "returned_count": 2,
        "has_more": False,
    }


def test_status_is_not_part_of_v1_input(api_client: TestClient) -> None:
    payload = {**_payload(), "status": "active"}

    response = api_client.post("/api/v1/recommend", json=payload)

    assert response.status_code == 422


def test_missing_signals_drive_guidance_without_product_output(
    api_client: TestClient,
    monkeypatch,
) -> None:
    payload = {
        "query": "cadeau",
        "limit": 24,
        "offset": 0,
    }
    monkeypatch.setattr(
        recommendation_pipeline,
        "candidate_generation_service",
        lambda request, query_understanding: {
            "_candidates": [],
            "total_candidates": 0,
            "filters_applied": {
                "stock": "stock > 0",
                "budget_max": request.budget_max,
                "hard_filters": request.hard_filters or {},
            },
        },
    )

    response = api_client.post("/api/v1/recommend", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["query_understanding"]["missing_signals"] == [
        "event",
        "relationship",
        "theme",
        "gift_benefit",
        "gift_type",
    ]
    assert all("product_id" not in idea for idea in body["related_ideas"])
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


def test_architecture_guard_rejects_pipeline_order_drift() -> None:
    guard = ArchitectureGuard()

    try:
        guard.mark_step("candidate_generation")
    except ArchitectureGuardError as exc:
        assert "Invalid pipeline order" in str(exc)
    else:
        raise AssertionError("ArchitectureGuardError was not raised.")


def test_architecture_guard_rejects_forbidden_response_fields() -> None:
    guard = ArchitectureGuard()
    for step in [
        "query_understanding",
        "suggested_reformulations",
        "candidate_generation",
        "best_matches",
        "similarity_ideas",
        "related_ideas",
        "response",
    ]:
        guard.mark_step(step)

    response = {
        "query_understanding": {
            "detected_signals": {
                "event": [],
                "relationship": [],
                "theme": [],
                "gift_benefit": [],
                "gift_type": [],
            },
            "confidence": {},
            "missing_signals": [],
        },
        "suggested_reformulations": [],
        "candidate_generation": {"total_candidates": 0, "filters_applied": {}},
        "best_matches": [{"product_id": "gift-1", "_score": 1.0}],
        "similarity_ideas": [],
        "related_ideas": [],
        "meta": {"limit": 24, "offset": 0, "returned_count": 1, "has_more": False},
    }

    try:
        guard.validate_response(response)
    except ArchitectureGuardError as exc:
        assert "Forbidden field '_score'" in str(exc)
    else:
        raise AssertionError("ArchitectureGuardError was not raised.")


def test_architecture_guard_rejects_related_ideas_with_products() -> None:
    guard = ArchitectureGuard()

    try:
        guard.validate_related_ideas([{"product_id": "gift-1"}])
    except ArchitectureGuardError as exc:
        assert "product_id" in str(exc)
    else:
        raise AssertionError("ArchitectureGuardError was not raised.")


def test_services_cannot_be_called_directly_outside_pipeline() -> None:
    try:
        query_understanding_service(RecommendationRequest(query="cadeau"))
    except ArchitectureGuardError as exc:
        assert "must be called through recommendation pipeline" in str(exc)
    else:
        raise AssertionError("ArchitectureGuardError was not raised.")


def test_recommendation_contract_rejects_unknown_gift_type(api_client: TestClient) -> None:
    payload = _payload()
    payload["soft_tags"]["gift_type"] = [{"slug": "random", "intensity": 1.0}]

    response = api_client.post("/api/v1/recommend", json=payload)

    assert response.status_code == 422
    assert "gift_type" in response.text


def test_gift_type_facet_registry_and_weight_are_configured() -> None:
    assert SOFT_FACET_SLUGS["gift_type"] == frozenset(
        {"coffret", "kit", "gift_card", "subscription", "experience"}
    )
    assert SOFT_FACET_DEFAULT_WEIGHTS["gift_type"] == 20.0
    assert SOFT_FACET_DEFAULT_WEIGHTS["gift_type"] > SOFT_FACET_DEFAULT_WEIGHTS["theme"]
    assert (
        SOFT_FACET_DEFAULT_WEIGHTS["gift_type"]
        > SOFT_FACET_DEFAULT_WEIGHTS["gift_benefit"]
    )


def test_recommendation_contract_rejects_non_taxonomy_gift_type_weight(
    api_client: TestClient,
) -> None:
    payload = _payload()
    payload["facet_weights"]["gift_type"] = 19.0

    response = api_client.post("/api/v1/recommend", json=payload)

    assert response.status_code == 422
    assert "facet_weights.gift_type" in response.text
