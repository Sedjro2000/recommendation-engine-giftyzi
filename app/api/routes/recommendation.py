from fastapi import APIRouter

from app.orchestrator.recommendation_pipeline import run_recommendation_pipeline
from app.schemas.recommendation import HealthResponse, RecommendationRequest, RecommendationResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    tags=["Health"],
)
def health() -> HealthResponse:
    return HealthResponse()


@router.post("/recommend", response_model=RecommendationResponse)
def recommend(request: RecommendationRequest) -> RecommendationResponse:
    return run_recommendation_pipeline(request)
