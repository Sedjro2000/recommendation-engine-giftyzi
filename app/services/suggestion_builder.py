from typing import Any

from app.api.schemas import RecommendRequest, RelatedIdea, SuggestedReformulation
from app.config.similarity_loader import load_all_similarity_tables
from app.services.exploration_service import (
    build_related_ideas,
    detect_missing_signals,
)
from app.services.reformulation_service import (
    build_global_explanation,
    build_suggested_reformulations,
)
from app.services.similarity_service import (
    DEFAULT_SIMILARITY_TOP_N,
    expand_similarity_values,
)


def _as_slug_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        if not all(isinstance(item, str) for item in value):
            raise ValueError("suggestion builder slugs must be strings")
        return value
    raise ValueError("suggestion builder values must be strings or lists of strings")


def _normalize_suggestion_input(input_data: dict[str, Any]) -> dict[str, list[str]]:
    """Map legacy builder input names onto the engine facet names."""
    return {
        "event": _as_slug_list(input_data.get("event")),
        "relationship": _as_slug_list(
            input_data.get("relationship", input_data.get("relation"))
        ),
        "theme": _as_slug_list(input_data.get("theme", input_data.get("tags"))),
        "gift_benefit": _as_slug_list(
            input_data.get(
                "gift_benefit",
                input_data.get("benefits", input_data.get("benefit")),
            )
        ),
    }


def suggestion_builder(
    input_data: dict[str, Any],
    *,
    limit: int = 10,
    top_n: int = DEFAULT_SIMILARITY_TOP_N,
    collection_name: str = "ProductRecommendationProjection",
    candidate_products: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Legacy compatibility facade.

    The builder no longer fetches, scores, or ranks products. Product ranking is
    owned only by ranking_service. This function preserves the legacy expansion
    output shape for callers that still import it.
    """
    del limit, collection_name, candidate_products
    normalized_input = _normalize_suggestion_input(input_data)
    tables = load_all_similarity_tables()
    expanded_query = {
        facet: expand_similarity_values(
            facet,
            slugs,
            tables.get(facet, {}),
            top_n=top_n,
        )
        for facet, slugs in normalized_input.items()
    }

    return {
        "input": normalized_input,
        "expanded_query": expanded_query,
        "results": [],
    }


def suggestionBuilder(input_data: dict[str, Any]) -> dict[str, Any]:
    """Compatibility wrapper for callers using the legacy camelCase name."""
    return suggestion_builder(input_data)


def build_related_ideas_with_suggestion_builder(
    request: RecommendRequest,
    candidate_products: list[dict[str, Any]],
) -> list[RelatedIdea]:
    """Compatibility wrapper; related ideas are exploration templates only."""
    del candidate_products
    return build_related_ideas(request)


__all__ = [
    "RelatedIdea",
    "SuggestedReformulation",
    "build_global_explanation",
    "build_related_ideas",
    "build_related_ideas_with_suggestion_builder",
    "build_suggested_reformulations",
    "detect_missing_signals",
    "expand_similarity_values",
    "suggestionBuilder",
    "suggestion_builder",
]
