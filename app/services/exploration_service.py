from typing import Any

from app.api.schemas import RecommendRequest, RelatedIdea

SOFT_SIGNAL_ORDER: tuple[str, ...] = (
    "event",
    "relationship",
    "theme",
    "gift_benefit",
)
MAX_RELATED_IDEAS = 2

RELATED_IDEA_TEMPLATES: dict[str, dict[str, Any]] = {
    "event": {
        "idea_id": "explore-without-specific-event",
        "title": "Explorer les cadeaux sans occasion precise",
        "reason": (
            "L'occasion n'est pas encore precisee. Une piste plus generale "
            "peut aider a explorer des idees cadeau."
        ),
        "soft_tags": {"event": ["juste-faire-plaisir"]},
    },
    "relationship": {
        "idea_id": "explore-for-close-recipient",
        "title": "Explorer les cadeaux pour un proche",
        "reason": (
            "Le lien avec la personne n'est pas encore precise. Une piste "
            "generale peut aider a rester pertinent sans modifier les contraintes."
        ),
        "soft_tags": {"relationship": ["un-proche"]},
    },
    "theme": {
        "idea_id": "explore-personalized-gifts",
        "title": "Explorer les cadeaux personnalises",
        "reason": (
            "Le style du cadeau n'est pas encore precise. Les cadeaux "
            "personnalises peuvent aider a mieux adapter la recommandation."
        ),
        "soft_tags": {"theme": ["personalized"]},
    },
    "gift_benefit": {
        "idea_id": "explore-memorable-gifts",
        "title": "Explorer les cadeaux memorables",
        "reason": (
            "L'effet recherche n'est pas encore precise. Les cadeaux memorables "
            "sont souvent pertinents dans un contexte cadeau."
        ),
        "soft_tags": {"gift_benefit": ["memorable"]},
    },
}


def soft_tag_slugs(request: RecommendRequest, facet: str) -> list[str]:
    items = getattr(request.soft_tags, facet)
    if not items:
        return []
    return [item.slug for item in items]


def detect_missing_signals(request: RecommendRequest) -> list[str]:
    return [
        facet
        for facet in SOFT_SIGNAL_ORDER
        if not soft_tag_slugs(request, facet)
    ]


def build_related_ideas(request: RecommendRequest) -> list[RelatedIdea]:
    ideas: list[RelatedIdea] = []
    for facet in detect_missing_signals(request):
        template = RELATED_IDEA_TEMPLATES[facet]
        ideas.append(
            RelatedIdea(
                idea_id=template["idea_id"],
                title=template["title"],
                reason=template["reason"],
                soft_tags=template["soft_tags"],
                hard_filters={},
            )
        )
        if len(ideas) >= MAX_RELATED_IDEAS:
            break
    return ideas
