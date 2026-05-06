from typing import Any

from app.api.schemas import (
    RecommendationExplanation,
    RecommendRequest,
    SuggestedReformulation,
)
from app.services.exploration_service import SOFT_SIGNAL_ORDER, detect_missing_signals

MAX_SUGGESTED_REFORMULATIONS = 3
LOW_RESULT_THRESHOLD = 3
LOW_SCORE_THRESHOLD = 0.25

REFORMULATION_TEMPLATES: dict[str, dict[str, str]] = {
    "event": {
        "label": "Preciser l'occasion",
        "query": "Cadeau pour un anniversaire",
        "reason": "L'occasion aide a mieux adapter les idees cadeau.",
    },
    "relationship": {
        "label": "Preciser le lien avec la personne",
        "query": "Cadeau pour un proche",
        "reason": "La relation aide a mieux classer les idees cadeau.",
    },
    "theme": {
        "label": "Preciser le style du cadeau",
        "query": "Cadeau personnalise",
        "reason": "Le style permet de proposer des idees plus proches de l'intention.",
    },
    "gift_benefit": {
        "label": "Preciser l'effet recherche",
        "query": "Cadeau memorable",
        "reason": (
            "L'effet recherche aide a distinguer un cadeau utile, emotionnel "
            "ou surprenant."
        ),
    },
}


def _soft_tag_slugs(request: RecommendRequest, facet: str) -> list[str]:
    items = getattr(request.soft_tags, facet)
    if not items:
        return []
    return [item.slug for item in items]


def _used_signal(name: str, signal_type: str, values: list[Any]) -> dict[str, Any]:
    return {
        "name": name,
        "type": signal_type,
        "values": values,
    }


def build_global_explanation(request: RecommendRequest) -> RecommendationExplanation:
    used_signals: list[dict[str, Any]] = [
        _used_signal("status", "hard", [request.status]),
    ]
    hard_constraints_respected = ["stock", "status"]

    if request.budget_max is not None:
        used_signals.append(_used_signal("budget_max", "hard", [request.budget_max]))
        hard_constraints_respected.insert(0, "budget_max")

    if request.hard_filters.recipient_gender:
        used_signals.append(
            _used_signal(
                "recipient_gender",
                "hard",
                request.hard_filters.recipient_gender,
            )
        )
        hard_constraints_respected.append("recipient_gender")
    if request.hard_filters.age_group:
        used_signals.append(
            _used_signal("age_group", "hard", request.hard_filters.age_group)
        )
        hard_constraints_respected.append("age_group")

    for facet in SOFT_SIGNAL_ORDER:
        slugs = _soft_tag_slugs(request, facet)
        if slugs:
            used_signals.append(_used_signal(facet, "soft", slugs))

    return RecommendationExplanation(
        summary=(
            "Recherche filtree par contraintes strictes, puis classee selon les "
            "preferences cadeau disponibles."
        ),
        used_signals=used_signals,
        missing_signals=detect_missing_signals(request),
        hard_constraints_respected=hard_constraints_respected,
    )


def build_suggested_reformulations(
    request: RecommendRequest,
    result_count: int,
    top_score: float | None = None,
) -> list[SuggestedReformulation]:
    suggestions: list[SuggestedReformulation] = []
    seen_queries: set[str] = set()

    def add(template: dict[str, str], source: str) -> None:
        if len(suggestions) >= MAX_SUGGESTED_REFORMULATIONS:
            return
        query = template["query"]
        if query in seen_queries:
            return
        seen_queries.add(query)
        suggestions.append(
            SuggestedReformulation(
                label=template["label"],
                query=query,
                reason=template["reason"],
                source=source,
            )
        )

    for facet in detect_missing_signals(request):
        add(REFORMULATION_TEMPLATES[facet], "missing_signal")

    if result_count < LOW_RESULT_THRESHOLD:
        for facet in detect_missing_signals(request):
            add(REFORMULATION_TEMPLATES[facet], "not_enough_results")

    if top_score is not None and top_score < LOW_SCORE_THRESHOLD:
        for facet in detect_missing_signals(request):
            add(REFORMULATION_TEMPLATES[facet], "low_confidence")

    return suggestions
