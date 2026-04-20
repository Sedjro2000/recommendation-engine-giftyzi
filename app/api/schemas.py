from typing import Any

from pydantic import BaseModel, Field


class RecommendRequest(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language gift query")
    budget_max: float = Field(..., gt=0, description="Maximum budget (inclusive)")


class RecommendResponse(BaseModel):
    best_matches: list[dict[str, Any]]
