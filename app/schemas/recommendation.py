from typing import Any

import math

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config.facets import (
    HARD_FACET_SLUGS,
    SOFT_FACET_DEFAULT_WEIGHTS,
    SOFT_FACET_SLUGS,
)


def _ensure_mapping(value: Any, field_name: str) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be an object")
    return value


def _ensure_slug_list(
    value: Any,
    *,
    field_name: str,
    allowed_slugs: frozenset[str],
) -> list[str]:
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list")

    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} items must be strings")
        if item not in allowed_slugs:
            raise ValueError(f"{field_name} contains unknown slug '{item}'")
        normalized.append(item)
    return normalized


def _ensure_finite_weight(value: Any, *, field_name: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise TypeError(f"{field_name} must be numeric")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field_name} must be finite")
    if numeric < 0:
        raise ValueError(f"{field_name} must be >= 0")
    return numeric


def _ensure_soft_tag_items(
    value: Any,
    *,
    field_name: str,
    allowed_slugs: frozenset[str],
) -> list[dict[str, float | str]]:
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a list")

    normalized: list[dict[str, float | str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise TypeError(f"{field_name}[{index}] must be an object")
        slug = item.get("slug")
        intensity = item.get("intensity")
        if not isinstance(slug, str):
            raise TypeError(f"{field_name}[{index}].slug must be a string")
        if slug not in allowed_slugs:
            raise ValueError(f"{field_name}[{index}] contains unknown slug '{slug}'")
        if not isinstance(intensity, int | float) or isinstance(intensity, bool):
            raise TypeError(f"{field_name}[{index}].intensity must be numeric")
        numeric_intensity = float(intensity)
        if not math.isfinite(numeric_intensity):
            raise ValueError(f"{field_name}[{index}].intensity must be finite")
        if numeric_intensity <= 0 or numeric_intensity > 1:
            raise ValueError(
                f"{field_name}[{index}].intensity must be > 0 and <= 1"
            )
        normalized.append({"slug": slug, "intensity": numeric_intensity})
    return normalized


class RecommendationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str | None = None
    budget_max: float | None = Field(default=None, ge=0.0)
    hard_filters: dict[str, Any] | None = None
    soft_tags: dict[str, Any] | None = None
    facet_weights: dict[str, Any] | None = None
    limit: int = Field(default=24, gt=0)
    offset: int = Field(default=0, ge=0)

    @field_validator("hard_filters", mode="before")
    @classmethod
    def validate_hard_filters(cls, value: Any) -> dict[str, Any] | None:
        hard_filters = _ensure_mapping(value, "hard_filters")
        if hard_filters is None:
            return None

        normalized: dict[str, Any] = {}
        for facet, raw_values in hard_filters.items():
            if facet not in HARD_FACET_SLUGS:
                raise ValueError(f"hard_filters.{facet} is not supported")
            normalized[facet] = _ensure_slug_list(
                raw_values,
                field_name=f"hard_filters.{facet}",
                allowed_slugs=HARD_FACET_SLUGS[facet],
            )
        return normalized

    @field_validator("soft_tags", mode="before")
    @classmethod
    def validate_soft_tags(cls, value: Any) -> dict[str, Any] | None:
        soft_tags = _ensure_mapping(value, "soft_tags")
        if soft_tags is None:
            return None

        normalized: dict[str, Any] = {}
        for facet, raw_items in soft_tags.items():
            if facet not in SOFT_FACET_SLUGS:
                raise ValueError(f"soft_tags.{facet} is not supported")
            normalized[facet] = _ensure_soft_tag_items(
                raw_items,
                field_name=f"soft_tags.{facet}",
                allowed_slugs=SOFT_FACET_SLUGS[facet],
            )
        return normalized

    @field_validator("facet_weights", mode="before")
    @classmethod
    def validate_facet_weights(cls, value: Any) -> dict[str, Any] | None:
        facet_weights = _ensure_mapping(value, "facet_weights")
        if facet_weights is None:
            return None

        normalized: dict[str, Any] = {}
        for facet, raw_weight in facet_weights.items():
            if facet not in SOFT_FACET_SLUGS:
                raise ValueError(f"facet_weights.{facet} is not supported")
            normalized_weight = _ensure_finite_weight(
                raw_weight,
                field_name=f"facet_weights.{facet}",
            )
            if (
                facet == "gift_type"
                and normalized_weight != SOFT_FACET_DEFAULT_WEIGHTS["gift_type"]
            ):
                raise ValueError(
                    "facet_weights.gift_type must be 20.0 to match the taxonomy weight"
                )
            normalized[facet] = normalized_weight
        return normalized


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
