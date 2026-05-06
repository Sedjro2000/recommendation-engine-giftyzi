from typing import Any

from app.config.similarity_loader import load_all_similarity_tables
from app.core.architecture_guard import assert_service_call_allowed

KNOWN_FACETS: tuple[str, ...] = ("event", "relationship", "theme", "gift_benefit")
SIMILARITY_IDEA_LIMIT = 3


def _product_id(product: dict[str, Any]) -> str | None:
    value = product.get("product_id")
    if value is None:
        return None
    return str(value)


def _tag_slugs(product: dict[str, Any], facet: str) -> list[str]:
    tags = product.get("tags", {}).get(facet, [])
    if not isinstance(tags, list):
        return []
    return [
        str(tag["slug"])
        for tag in tags
        if isinstance(tag, dict) and tag.get("slug")
    ]


def _known_similarity_slugs(table: dict[str, dict[str, float]]) -> set[str]:
    return set(table) | {slug for row in table.values() for slug in row}


def _tag_similarity(
    source_slug: str,
    target_slug: str,
    table: dict[str, dict[str, float]],
) -> float:
    known_slugs = _known_similarity_slugs(table)
    if source_slug not in known_slugs or target_slug not in known_slugs:
        return 0.0
    if source_slug == target_slug:
        return 1.0
    return float(table.get(source_slug, {}).get(target_slug, 0.0))


def _facet_similarity(
    source: dict[str, Any],
    target: dict[str, Any],
    facet: str,
    table: dict[str, dict[str, float]],
) -> float | None:
    source_slugs = _tag_slugs(source, facet)
    target_slugs = _tag_slugs(target, facet)
    if not source_slugs or not target_slugs:
        return None

    best = 0.0
    for source_slug in source_slugs:
        for target_slug in target_slugs:
            best = max(best, _tag_similarity(source_slug, target_slug, table))
    return best


def _product_similarity(
    source: dict[str, Any],
    target: dict[str, Any],
    tables: dict[str, dict[str, dict[str, float]]],
) -> float:
    facet_scores: list[float] = []
    for facet in KNOWN_FACETS:
        score = _facet_similarity(source, target, facet, tables.get(facet, {}))
        if score is not None:
            facet_scores.append(score)

    if not facet_scores:
        return 0.0
    similarity = sum(facet_scores) / len(facet_scores)
    return max(0.0, min(1.0, similarity))


def similarity_service(best_matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    assert_service_call_allowed("similarity_ideas")
    tables = load_all_similarity_tables()
    ideas: list[dict[str, Any]] = []
    used_product_ids: set[str] = set()

    for source_index, source in enumerate(best_matches):
        source_id = _product_id(source)
        if source_id is None:
            continue
        for target in best_matches[source_index + 1 :]:
            target_id = _product_id(target)
            if target_id is None or target_id in used_product_ids:
                continue

            similarity_score = _product_similarity(source, target, tables)
            if similarity_score <= 0:
                continue

            ideas.append(
                {
                    "product_id": target_id,
                    "source_product_id": source_id,
                    "similarity_score": similarity_score,
                    "reason": "Similarite UX basee uniquement sur les tags produit.",
                }
            )
            used_product_ids.add(target_id)

    ideas.sort(
        key=lambda idea: (-idea["similarity_score"], idea["product_id"]),
    )
    return ideas[:SIMILARITY_IDEA_LIMIT]
