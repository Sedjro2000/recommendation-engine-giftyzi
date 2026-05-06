from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = None
    budget_max: float | None = Field(default=None, ge=0.0)
    hard_filters: dict[str, Any] | None = None
    soft_tags: dict[str, Any] | None = None
    facet_weights: dict[str, Any] | None = None
    limit: int = Field(default=24, gt=0)
    offset: int = Field(default=0, ge=0)


class RecommendationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_understanding: dict[str, Any]
    suggested_reformulations: list[Any]
    candidate_generation: dict[str, Any]
    best_matches: list[dict[str, Any]]
    similarity_ideas: list[Any]
    related_ideas: list[Any]
    meta: dict[str, Any]


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "ok"
    service: str = "GIFTYZI Recommendation Engine"
    version: str = "0.1.0"
