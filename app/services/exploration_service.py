from typing import Any

from app.core.architecture_guard import assert_service_call_allowed

MAX_RELATED_IDEAS = 2

RELATED_IDEA_TEMPLATES: dict[str, dict[str, Any]] = {
    "event": {
        "idea_id": "explore-event",
        "title": "Explorer par occasion",
        "reason": "Une occasion peut ouvrir des pistes cadeau plus ciblees.",
        "soft_tags": {"event": ["TODO"]},
    },
    "relationship": {
        "idea_id": "explore-relationship",
        "title": "Explorer par relation",
        "reason": "La relation peut aider a varier les pistes cadeau.",
        "soft_tags": {"relationship": ["TODO"]},
    },
    "theme": {
        "idea_id": "explore-theme",
        "title": "Explorer par theme",
        "reason": "Un theme peut aider a explorer une intention plus precise.",
        "soft_tags": {"theme": ["TODO"]},
    },
}


def exploration_service(query_understanding: dict[str, Any]) -> list[dict[str, Any]]:
    assert_service_call_allowed("related_ideas")
    ideas: list[dict[str, Any]] = []
    for signal in query_understanding.get("missing_signals", []):
        template = RELATED_IDEA_TEMPLATES.get(signal)
        if template is None:
            continue
        ideas.append(template)
        if len(ideas) >= MAX_RELATED_IDEAS:
            break
    return ideas
