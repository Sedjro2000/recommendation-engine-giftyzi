from typing import Any

from app.core.architecture_guard import assert_service_call_allowed

MAX_SUGGESTED_REFORMULATIONS = 3

REFORMULATION_TEMPLATES: dict[str, dict[str, str]] = {
    "event": {
        "label": "Preciser l'occasion",
        "reason": "L'occasion manque pour guider la recherche.",
    },
    "relationship": {
        "label": "Preciser le lien",
        "reason": "Le lien avec la personne manque pour guider la recherche.",
    },
    "theme": {
        "label": "Preciser le theme",
        "reason": "Le theme manque pour guider la recherche.",
    },
}


def reformulation_service(query_understanding: dict[str, Any]) -> list[dict[str, str]]:
    assert_service_call_allowed("suggested_reformulations")
    suggestions: list[dict[str, str]] = []
    for signal in query_understanding.get("missing_signals", []):
        template = REFORMULATION_TEMPLATES.get(signal)
        if template is None:
            continue
        suggestions.append(
            {
                "label": template["label"],
                "reason": template["reason"],
                "source": "missing_signal",
            }
        )
        if len(suggestions) >= MAX_SUGGESTED_REFORMULATIONS:
            break
    return suggestions
