from typing import Any

from app.api.schemas import (
    RecommendationExplanation,
    RecommendRequest,
    RelatedIdea,
    SuggestedReformulation,
)

SOFT_SIGNAL_ORDER: tuple[str, ...] = (
    "event",
    "relationship",
    "theme",
    "gift_benefit",
)
MAX_SUGGESTED_REFORMULATIONS = 3
MAX_RELATED_IDEAS = 2

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

RELATED_IDEA_TEMPLATES: dict[str, dict[str, Any]] = {
    "event": {
        "title": "Explorer les cadeaux sans occasion precise",
        "reason": (
            "L'occasion n'est pas encore precisee. Une piste plus generale "
            "peut aider a explorer des idees cadeau."
        ),
        "soft_tags": {"event": ["juste-faire-plaisir"]},
    },
    "relationship": {
        "title": "Explorer les cadeaux pour un proche",
        "reason": (
            "Le lien avec la personne n'est pas encore precise. Une piste "
            "generale peut aider a rester pertinent sans modifier les contraintes."
        ),
        "soft_tags": {"relationship": ["un-proche"]},
    },
    "theme": {
        "title": "Explorer les cadeaux personnalises",
        "reason": (
            "Le style du cadeau n'est pas encore precise. Les cadeaux "
            "personnalises peuvent aider a mieux adapter la recommandation."
        ),
        "soft_tags": {"theme": ["personalized"]},
    },
    "gift_benefit": {
        "title": "Explorer les cadeaux memorables",
        "reason": (
            "L'effet recherche n'est pas encore precise. Les cadeaux memorables "
            "sont souvent pertinents dans un contexte cadeau."
        ),
        "soft_tags": {"gift_benefit": ["memorable"]},
    },
}


def _soft_tag_slugs(request: RecommendRequest, facet: str) -> list[str]:
    items = getattr(request.soft_tags, facet)
    if not items:
        return []
    return [item.slug for item in items]


def detect_missing_signals(request: RecommendRequest) -> list[str]:
    return [
        facet
        for facet in SOFT_SIGNAL_ORDER
        if not _soft_tag_slugs(request, facet)
    ]


def _used_signal(name: str, signal_type: str, values: list[Any]) -> dict[str, Any]:
    return {
        "name": name,
        "type": signal_type,
        "values": values,
    }


def build_global_explanation(request: RecommendRequest) -> RecommendationExplanation:
    used_signals: list[dict[str, Any]] = [
        _used_signal("status", "hard", [request.status]),
        _used_signal("budget_max", "hard", [request.price]),
    ]
    hard_constraints_respected = ["budget_max", "stock", "status"]

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

    missing_signals = detect_missing_signals(request)
    summary = (
        "Recherche filtree par contraintes strictes, puis classee selon les "
        "preferences cadeau disponibles."
    )

    return RecommendationExplanation(
        summary=summary,
        used_signals=used_signals,
        missing_signals=missing_signals,
        hard_constraints_respected=hard_constraints_respected,
    )


def build_suggested_reformulations(
    request: RecommendRequest,
    result_count: int,
) -> list[SuggestedReformulation]:
    suggestions: list[SuggestedReformulation] = []
    for facet in detect_missing_signals(request):
        template = REFORMULATION_TEMPLATES[facet]
        suggestions.append(
            SuggestedReformulation(
                label=template["label"],
                query=template["query"],
                reason=template["reason"],
                source="missing_signal",
            )
        )
        if len(suggestions) >= MAX_SUGGESTED_REFORMULATIONS:
            break
    return suggestions


def build_related_ideas(request: RecommendRequest) -> list[RelatedIdea]:
    ideas: list[RelatedIdea] = []
    for facet in detect_missing_signals(request):
        template = RELATED_IDEA_TEMPLATES[facet]
        ideas.append(
            RelatedIdea(
                title=template["title"],
                reason=template["reason"],
                soft_tags=template["soft_tags"],
                hard_filters={},
            )
        )
        if len(ideas) >= MAX_RELATED_IDEAS:
            break
    return ideas
