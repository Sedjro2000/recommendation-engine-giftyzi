import math
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config.facets import HARD_FACET_SLUGS, OUT_OF_SCOPE_FACET_SLUGS, SOFT_FACET_SLUGS

VALID_INTENSITIES: frozenset[float] = frozenset({0.25, 0.5, 0.75, 1.0})


def _is_canonical_slug(slug: str) -> bool:
    return (
        slug == slug.lower()
        and slug.isascii()
        and " " not in slug
        and "_" not in slug
    )


def _out_of_scope_facet_for_slug(slug: str) -> str | None:
    for facet, slugs in OUT_OF_SCOPE_FACET_SLUGS.items():
        if slug in slugs:
            return facet
    return None


def _validate_slug_for_facet(facet: str, slug: str, allowed: frozenset[str]) -> None:
    out_of_scope_facet = _out_of_scope_facet_for_slug(slug)
    if out_of_scope_facet is not None:
        raise ValueError(
            f"slug '{slug}' belongs to out-of-scope facet '{out_of_scope_facet}', "
            f"not engine v1 facet '{facet}'"
        )
    if not _is_canonical_slug(slug):
        raise ValueError(f"slug '{slug}' is not canonical for facet '{facet}'")
    if slug not in allowed:
        raise ValueError(f"unknown slug '{slug}' for facet '{facet}'")


class SoftTagItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(..., min_length=1)
    intensity: float

    @field_validator("intensity")
    @classmethod
    def intensity_must_be_valid(cls, v: float) -> float:
        if v not in VALID_INTENSITIES:
            raise ValueError(
                f"intensity must be one of {sorted(VALID_INTENSITIES)}, got {v}"
            )
        return v


class HardFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    age_group: list[str] | None = None
    recipient_gender: list[str] | None = None

    @field_validator("age_group", "recipient_gender")
    @classmethod
    def hard_filter_slugs_must_be_known(
        cls,
        v: list[str] | None,
        info: Any,
    ) -> list[str] | None:
        if v is None:
            return v
        facet = info.field_name
        allowed = HARD_FACET_SLUGS[facet]
        for slug in v:
            _validate_slug_for_facet(facet, slug, allowed)
        return v


class SoftTags(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: list[SoftTagItem] | None = None
    relationship: list[SoftTagItem] | None = None
    theme: list[SoftTagItem] | None = None
    gift_benefit: list[SoftTagItem] | None = None

    @model_validator(mode="after")
    def soft_tag_slugs_must_be_known(self) -> "SoftTags":
        for facet, allowed in SOFT_FACET_SLUGS.items():
            items: list[SoftTagItem] | None = getattr(self, facet)
            if not items:
                continue
            for item in items:
                _validate_slug_for_facet(facet, item.slug, allowed)
        return self


class FacetWeights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    relationship: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    theme: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)
    gift_benefit: float | None = Field(default=None, ge=0.0, allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def facet_weights_must_not_contain_null(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for facet, value in data.items():
                if value is None:
                    raise ValueError(f"facet_weights.{facet} must not be null")
        return data

    @field_validator("event", "relationship", "theme", "gift_benefit")
    @classmethod
    def facet_weight_must_be_finite(cls, v: float | None, info: Any) -> float | None:
        if v is None:
            return v
        if not math.isfinite(v):
            raise ValueError(f"facet_weights.{info.field_name} must be finite")
        return v


class RecommendRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., min_length=1)
    price: float = Field(..., ge=0.0)
    hard_filters: HardFilters = Field(default_factory=HardFilters)
    soft_tags: SoftTags = Field(default_factory=SoftTags)
    facet_weights: FacetWeights = Field(default_factory=FacetWeights)


class QueryInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    normalized_query: str | None = None
    detected_signals: dict[str, Any] = Field(default_factory=dict)
    confidence: dict[str, Any] = Field(default_factory=dict)


class HardConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    budget_max: float
    availability: str
    recipient_gender: list[str] | None = None
    age_group: list[str] | None = None


class SoftPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: list[str] | None = None
    relationship: list[str] | None = None
    theme: list[str] | None = None
    gift_benefit: list[str] | None = None
    facet_weights: dict[str, float] = Field(default_factory=dict)


class RecommendationFallback(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    message: str


class RecommendationMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_count: int = Field(..., ge=0)
    limit: int | None = Field(default=None, ge=0)
    contract_version: str = "recommendation_public_v1"


class RecommendationDebugInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scoring_formula: str
    stock_filter: str
    exact_match_score: float


class RecommendResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query_interpretation: QueryInterpretation
    hard_constraints: HardConstraints
    soft_preferences: SoftPreferences
    best_matches: list[dict[str, Any]]
    related_ideas: list[dict[str, Any]]
    relaxations_applied: list[dict[str, Any]]
    suggested_reformulations: list[str]
    fallback: RecommendationFallback | None
    meta: RecommendationMeta
    debug_info: RecommendationDebugInfo
