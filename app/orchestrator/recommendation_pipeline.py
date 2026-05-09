import logging
from typing import Any

from app.core.architecture_guard import ArchitectureGuard
from app.schemas.recommendation import RecommendationRequest, RecommendationResponse
from app.services.best_matches_service import best_matches_service
from app.services.candidate_generation_service import candidate_generation_service
from app.services.exploration_service import exploration_service
from app.services.query_understanding_service import query_understanding_service
from app.services.reformulation_service import reformulation_service
from app.services.similarity_service import similarity_service


logger = logging.getLogger(__name__)


def build_response(
    request: RecommendationRequest,
    query_understanding: dict[str, Any],
    suggested_reformulations: list[Any],
    candidate_generation: dict[str, Any],
    best_matches: list[dict[str, Any]],
    similarity_ideas: list[Any],
    related_ideas: list[Any],
) -> RecommendationResponse:
    total_candidates = int(candidate_generation.get("total_candidates", 0))
    returned_count = len(best_matches)
    has_more = request.offset + returned_count < total_candidates
    public_candidate_generation = {
        key: value
        for key, value in candidate_generation.items()
        if not key.startswith("_")
    }

    return RecommendationResponse(
        query_understanding=query_understanding,
        suggested_reformulations=suggested_reformulations,
        candidate_generation=public_candidate_generation,
        best_matches=best_matches,
        similarity_ideas=similarity_ideas,
        related_ideas=related_ideas,
        meta={
            "limit": request.limit,
            "offset": request.offset,
            "returned_count": returned_count,
            "has_more": has_more,
        },
    )


def run_recommendation_pipeline(request: RecommendationRequest) -> RecommendationResponse:
    guard = ArchitectureGuard()
    guard.validate_request(request)

    with guard.pipeline_context():
        guard.mark_step("query_understanding")
        query_understanding = query_understanding_service(request)
        guard.validate_query_understanding(query_understanding)

        guard.mark_step("suggested_reformulations")
        suggested_reformulations = reformulation_service(query_understanding)
        guard.validate_suggested_reformulations(suggested_reformulations)

        guard.mark_step("candidate_generation")
        candidates = candidate_generation_service(request, query_understanding)
        guard.validate_candidate_generation(candidates)

        guard.mark_step("best_matches")
        best_matches = best_matches_service(candidates, request)
        guard.validate_best_matches(best_matches)

        guard.mark_step("similarity_ideas")
        similarity_ideas = similarity_service(best_matches)
        guard.validate_similarity_ideas(similarity_ideas)

        guard.mark_step("related_ideas")
        related_ideas = exploration_service(query_understanding)
        guard.validate_related_ideas(related_ideas)

        guard.mark_step("response")
        response = build_response(
            request,
            query_understanding,
            suggested_reformulations,
            candidates,
            best_matches,
            similarity_ideas,
            related_ideas,
        )
        guard.validate_response(response)
        logger.debug(
            "[pipeline] Final response.best_matches length=%d (limit=%d, offset=%d, has_more=%s).",
            len(best_matches),
            request.limit,
            request.offset,
            response.meta.get("has_more"),
        )
        return response
