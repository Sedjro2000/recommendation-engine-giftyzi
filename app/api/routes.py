import logging

from fastapi import APIRouter, HTTPException

from app.api.schemas import RecommendRequest, RecommendResponse
from app.services.recommendation_service import build_recommendation_response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/recommend", response_model=RecommendResponse)
def recommend(request: RecommendRequest) -> RecommendResponse:
    logger.info(
        f"[API] POST /recommend | price={request.price} | status='{request.status}'"
    )
    try:
        response = build_recommendation_response(request)
    except Exception as exc:
        logger.exception(f"[API] Unexpected error in /recommend: {exc}")
        raise HTTPException(status_code=500, detail="Internal recommendation error.")

    logger.info(f"[API] /recommend → returning {response.meta.result_count} results.")
    return response
