import logging
from typing import Any

from app.services.query_interpreter import QueryContext

logger = logging.getLogger(__name__)

DEFAULT_INTENSITY = 1.0

FACET_WEIGHTS: dict[str, float] = {
    "event": 0.5,
    "relationship": 0.3,
    "theme": 0.2,
}


def _best_tag_match(
    user_value: str,
    product_tags: list[dict[str, Any]],
    table: dict[str, dict[str, float]],
    weight: float,
) -> dict[str, Any] | None:
    """Return the tag entry that yields max sim × intensity, or None if no match."""
    user_row: dict[str, float] = table.get(user_value, {})
    if not user_row or not product_tags:
        return None

    best: dict[str, Any] | None = None
    best_score: float = 0.0

    for tag in product_tags:
        slug: str = tag.get("slug", "")
        if not slug:
            continue
        intensity: float = tag.get("intensity", DEFAULT_INTENSITY)
        sim: float = user_row.get(slug, 0.0)
        match: float = sim * intensity
        if match > best_score:
            best_score = match
            best = {
                "user_value": user_value,
                "best_tag": slug,
                "sim": round(sim, 4),
                "intensity": round(intensity, 4),
                "match": round(match, 4),
                "contribution": round(weight * match, 4),
            }

    return best


def build_explanation(
    product: dict[str, Any],
    context: QueryContext,
    tables: dict[str, dict[str, dict[str, float]]],
) -> dict[str, Any]:
    """
    Build a per-facet explanation for why a product was recommended.

    Returns:
        {
            "facets": {
                "event": {"user_value": ..., "best_tag": ..., "sim": ...,
                          "intensity": ..., "match": ..., "contribution": ...},
                "relationship": None,  # user did not request this facet
                "theme": None,
            },
            "summary": "Recommandé pour : event:anniversaire (100%)",
            "legacy": False           # True when occasion_score fallback was used
        }
    """
    product_tags: dict[str, list[dict[str, Any]]] = product.get("tags", {})

    # ── Legacy fallback ──────────────────────────────────────────────────────
    if not product_tags and "occasion_score" in product:
        occasion_scores: dict[str, float] = product["occasion_score"]
        event = context.get("event")
        if event and event in occasion_scores:
            score = occasion_scores[event]
            summary = f"[legacy] {event}: {score:.0%}"
        elif occasion_scores:
            avg = sum(occasion_scores.values()) / len(occasion_scores)
            summary = f"[legacy] moyenne occasions: {avg:.0%}"
        else:
            summary = "[legacy] aucun score disponible"
        logger.debug(f"[Explainer] '{product.get('name')}' → {summary}")
        return {"facets": {}, "summary": summary, "legacy": True}

    # ── New per-facet explanation ─────────────────────────────────────────────
    facets: dict[str, dict[str, Any] | None] = {}
    reasons: list[str] = []

    for facet, weight in FACET_WEIGHTS.items():
        user_value: str | None = context.get(facet)
        if user_value is None:
            facets[facet] = None
            continue

        facet_tags: list[dict[str, Any]] = product_tags.get(facet, [])
        table: dict[str, dict[str, float]] = tables.get(facet, {})
        entry = _best_tag_match(user_value, facet_tags, table, weight)

        if entry:
            facets[facet] = entry
            reasons.append(f"{facet}:{entry['best_tag']} ({entry['match']:.0%})")
        else:
            facets[facet] = {
                "user_value": user_value,
                "best_tag": None,
                "match": 0.0,
                "contribution": 0.0,
            }

    summary = (
        "Recommandé pour : " + ", ".join(reasons)
        if reasons
        else "Aucune correspondance trouvée"
    )
    logger.debug(f"[Explainer] '{product.get('name')}' → {summary}")
    return {"facets": facets, "summary": summary, "legacy": False}
