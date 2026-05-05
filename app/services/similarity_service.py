from typing import Any

from app.api.schemas import SimilarityIdea

DEFAULT_SIMILARITY_TOP_N = 3
DEFAULT_SIMILARITY_IDEA_LIMIT = 3
SIMILARITY_SOURCE_LIMIT = 3
KNOWN_FACETS: tuple[str, ...] = ("event", "relationship", "theme", "gift_benefit")


def known_similarity_slugs(table: dict[str, dict[str, float]]) -> set[str]:
    return set(table) | {slug for row in table.values() for slug in row}


def expand_similarity_values(
    facet: str,
    slugs: list[str],
    table: dict[str, dict[str, float]],
    top_n: int = DEFAULT_SIMILARITY_TOP_N,
) -> dict[str, float]:
    """Return direct and top-N similar slugs with their similarity weights."""
    if not slugs:
        return {}

    known_slugs = known_similarity_slugs(table)
    expanded: dict[str, float] = {}
    for slug in slugs:
        if slug not in known_slugs:
            raise ValueError(f"unknown similarity slug '{slug}' for facet '{facet}'")

        row = table.get(slug, {slug: 1.0})
        ranked_values = sorted(row.items(), key=lambda item: (-item[1], item[0]))
        for target_slug, similarity in ranked_values[:top_n]:
            expanded[target_slug] = max(expanded.get(target_slug, 0.0), similarity)

    return expanded


def _product_id(product: dict[str, Any]) -> str | None:
    value = product.get("product_id")
    if value is None:
        return None
    return str(value)


def _product_tag_slugs(product: dict[str, Any], facet: str) -> list[str]:
    tags = product.get("tags", {}).get(facet, [])
    if not isinstance(tags, list):
        return []
    return [
        str(tag["slug"])
        for tag in tags
        if isinstance(tag, dict) and tag.get("slug")
    ]


def _candidate_similarity_to_source(
    candidate: dict[str, Any],
    source: dict[str, Any],
    tables: dict[str, dict[str, dict[str, float]]],
) -> float:
    best = 0.0
    for facet in KNOWN_FACETS:
        table = tables.get(facet, {})
        source_slugs = _product_tag_slugs(source, facet)
        candidate_slugs = _product_tag_slugs(candidate, facet)
        if not source_slugs or not candidate_slugs:
            continue
        expanded = expand_similarity_values(facet, source_slugs, table)
        for slug in candidate_slugs:
            best = max(best, expanded.get(slug, 0.0))
    return max(0.0, min(1.0, best))


def build_similarity_ideas(
    best_matches: list[dict[str, Any]],
    ranked_candidates: list[dict[str, Any]],
    tables: dict[str, dict[str, dict[str, float]]],
    *,
    limit: int = DEFAULT_SIMILARITY_IDEA_LIMIT,
) -> list[SimilarityIdea]:
    """
    Build product-based similarity ideas from already-ranked candidates.

    This does not run a second catalog ranker. Candidates keep the single ranking
    engine order; similarity is only used to filter/annotate product ideas.
    """
    if not best_matches or not ranked_candidates:
        return []

    best_ids = {_product_id(product) for product in best_matches}
    source_matches = best_matches[:SIMILARITY_SOURCE_LIMIT]
    ideas: list[SimilarityIdea] = []
    used_ids: set[str] = set()

    for candidate in ranked_candidates:
        candidate_id = _product_id(candidate)
        if candidate_id is None or candidate_id in best_ids or candidate_id in used_ids:
            continue

        best_source_id: str | None = None
        best_similarity = 0.0
        for source in source_matches:
            source_id = _product_id(source)
            if source_id is None:
                continue
            similarity = _candidate_similarity_to_source(candidate, source, tables)
            if similarity > best_similarity:
                best_similarity = similarity
                best_source_id = source_id

        if best_similarity <= 0:
            continue

        ideas.append(
            SimilarityIdea(
                product_id=candidate_id,
                score=best_similarity,
                reason="Similar to a top-ranked gift through configured similarity tables.",
                source_product_id=best_source_id,
            )
        )
        used_ids.add(candidate_id)
        if len(ideas) >= limit:
            break

    return ideas
