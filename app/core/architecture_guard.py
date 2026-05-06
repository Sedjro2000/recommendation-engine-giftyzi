import inspect
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

EXPECTED_PIPELINE = [
    "query_understanding",
    "suggested_reformulations",
    "candidate_generation",
    "best_matches",
    "similarity_ideas",
    "related_ideas",
    "response",
]

FORBIDDEN_FIELDS = [
    "debug_info",
    "fallback",
    "hard_constraints",
    "soft_preferences",
    "query_interpretation",
    "_score",
    "ranking_debug",
]

SCORING_FIELDS = {"score", "_score", "_raw_score", "_max_possible_score", "ranking"}
SCORING_ALLOWED_MODULE = "app.services.best_matches_service"
SCORING_FORBIDDEN_MODULE_PARTS = (
    "candidate_generation",
    "similarity",
    "query_understanding",
    "exploration",
)
RELATED_IDEA_FORBIDDEN_FIELDS = {"product_id", "price", "score", "ranking"}
_ACTIVE_PIPELINE_STEP: ContextVar[str | None] = ContextVar(
    "active_pipeline_step",
    default=None,
)
_PIPELINE_CONTEXT_ACTIVE: ContextVar[bool] = ContextVar(
    "pipeline_context_active",
    default=False,
)


class ArchitectureGuardError(RuntimeError):
    pass


def _to_plain_data(data: Any) -> Any:
    if isinstance(data, BaseModel):
        return data.model_dump()
    return data


def _iter_field_paths(data: Any, prefix: str = ""):
    data = _to_plain_data(data)
    if isinstance(data, dict):
        for key, value in data.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path, key
            yield from _iter_field_paths(value, path)
    elif isinstance(data, list):
        for index, value in enumerate(data):
            path = f"{prefix}[{index}]"
            yield from _iter_field_paths(value, path)


def _assert_no_fields(data: Any, forbidden_fields: set[str], *, context: str) -> None:
    for path, key in _iter_field_paths(data):
        if key in forbidden_fields:
            raise ArchitectureGuardError(
                f"Forbidden field '{key}' detected in {context} at '{path}'."
            )


def assert_no_scoring_outside_best_matches(call_stack: Any | None = None) -> None:
    stack = call_stack if call_stack is not None else inspect.stack()
    for frame in stack:
        module = inspect.getmodule(frame.frame)
        module_name = module.__name__ if module is not None else ""
        if module_name == SCORING_ALLOWED_MODULE:
            return
        if any(part in module_name for part in SCORING_FORBIDDEN_MODULE_PARTS):
            raise ArchitectureGuardError(
                f"Scoring is forbidden in module '{module_name}'."
            )


def assert_related_ideas_no_products(data: Any) -> None:
    _assert_no_fields(
        data,
        RELATED_IDEA_FORBIDDEN_FIELDS,
        context="related_ideas",
    )


def assert_service_call_allowed(step: str) -> None:
    if not _PIPELINE_CONTEXT_ACTIVE.get():
        raise ArchitectureGuardError(
            f"Service for step '{step}' must be called through recommendation pipeline."
        )
    active_step = _ACTIVE_PIPELINE_STEP.get()
    if active_step != step:
        raise ArchitectureGuardError(
            f"Invalid service call for step '{step}' while active step is '{active_step}'."
        )


@dataclass
class ArchitectureGuard:
    executed_steps: list[str] = field(default_factory=list)

    @contextmanager
    def pipeline_context(self):
        active_token = _PIPELINE_CONTEXT_ACTIVE.set(True)
        step_token = _ACTIVE_PIPELINE_STEP.set(None)
        try:
            yield
        finally:
            _ACTIVE_PIPELINE_STEP.reset(step_token)
            _PIPELINE_CONTEXT_ACTIVE.reset(active_token)

    def mark_step(self, step: str) -> None:
        if step not in EXPECTED_PIPELINE:
            raise ArchitectureGuardError(f"Unknown pipeline step '{step}'.")
        self.executed_steps.append(step)
        _ACTIVE_PIPELINE_STEP.set(step)
        self.validate_pipeline_order(partial=True)

    def validate_pipeline_order(self, *, partial: bool = False) -> None:
        expected = EXPECTED_PIPELINE[: len(self.executed_steps)]
        if self.executed_steps != expected:
            raise ArchitectureGuardError(
                "Invalid pipeline order: "
                f"expected {expected}, got {self.executed_steps}."
            )
        if len(set(self.executed_steps)) != len(self.executed_steps):
            raise ArchitectureGuardError(
                f"Duplicated pipeline step detected: {self.executed_steps}."
            )
        if not partial and self.executed_steps != EXPECTED_PIPELINE:
            raise ArchitectureGuardError(
                "Incomplete pipeline: "
                f"expected {EXPECTED_PIPELINE}, got {self.executed_steps}."
            )

    def validate_request(self, request: Any) -> None:
        _assert_no_fields(request, set(FORBIDDEN_FIELDS), context="request")

    def validate_query_understanding(self, query_understanding: dict[str, Any]) -> None:
        expected_keys = {"detected_signals", "confidence", "missing_signals"}
        if set(query_understanding) != expected_keys:
            raise ArchitectureGuardError(
                "Invalid query_understanding shape: "
                f"expected {expected_keys}, got {set(query_understanding)}."
            )
        _assert_no_fields(
            query_understanding,
            set(FORBIDDEN_FIELDS) | SCORING_FIELDS,
            context="query_understanding",
        )

    def validate_suggested_reformulations(self, data: Any) -> None:
        _assert_no_fields(
            data,
            set(FORBIDDEN_FIELDS) | SCORING_FIELDS,
            context="suggested_reformulations",
        )

    def validate_candidate_generation(self, data: dict[str, Any]) -> None:
        public_data = {
            key: value
            for key, value in data.items()
            if not str(key).startswith("_")
        }
        _assert_no_fields(
            public_data,
            set(FORBIDDEN_FIELDS) | SCORING_FIELDS,
            context="candidate_generation",
        )

    def validate_best_matches(self, data: Any) -> None:
        _assert_no_fields(data, set(FORBIDDEN_FIELDS), context="best_matches")

    def validate_similarity_ideas(self, data: Any) -> None:
        _assert_no_fields(
            data,
            set(FORBIDDEN_FIELDS) | SCORING_FIELDS,
            context="similarity_ideas",
        )

    def validate_related_ideas(self, data: Any) -> None:
        _assert_no_fields(data, set(FORBIDDEN_FIELDS), context="related_ideas")
        assert_related_ideas_no_products(data)

    def validate_response(self, response: Any) -> None:
        self.validate_pipeline_order()
        plain = _to_plain_data(response)
        _assert_no_fields(plain, set(FORBIDDEN_FIELDS), context="response")
        if plain.get("best_matches") is None:
            raise ArchitectureGuardError("response.best_matches must not be None.")
        self.validate_query_understanding(plain.get("query_understanding", {}))
        self.validate_suggested_reformulations(
            plain.get("suggested_reformulations", []),
        )
        self.validate_candidate_generation(plain.get("candidate_generation", {}))
        self.validate_best_matches(plain.get("best_matches", []))
        self.validate_similarity_ideas(plain.get("similarity_ideas", []))
        self.validate_related_ideas(plain.get("related_ideas", []))
