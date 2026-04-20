import logging

from fastapi import APIRouter, HTTPException

from app.api.schemas import RecommendRequest, RecommendResponse
from app.services.recommendation_service import get_recommendations

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/recommend", response_model=RecommendResponse)
def recommend(request: RecommendRequest) -> RecommendResponse:
    logger.info(
        f"[API] POST /recommend | query='{request.query}' | budget_max={request.budget_max}"
    )
    try:
        results = get_recommendations(request.query, request.budget_max)
    except Exception as exc:
        logger.exception(f"[API] Unexpected error in /recommend: {exc}")
        raise HTTPException(status_code=500, detail="Internal recommendation error.")

    logger.info(f"[API] /recommend → returning {len(results)} results.")
    return RecommendResponse(best_matches=results)
