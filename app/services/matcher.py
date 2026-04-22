import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_INTENSITY = 1.0


def compute_match(
    user_value: str,
    product_tags: list[dict[str, Any]],
    similarity_table: dict[str, dict[str, float]],
) -> float:
    """Compute the match score for one facet.

    Formula:
        match = max( similarity(user_value, tag["slug"]) × tag["intensity"] )

    Args:
        user_value:       The value extracted from the user query for this facet
                          (e.g. "anniversaire" for the event facet).
        product_tags:     List of tag dicts attached to the product for this facet.
                          Each dict must have a "slug" key; "intensity" is optional
                          and defaults to DEFAULT_INTENSITY (1.0) when absent.
        similarity_table: The loaded similarity table for this facet
                          (dict[user_value -> dict[product_tag -> float]]).

    Returns:
        A float in [0.0, 1.0].
        Returns 0.0 when:
          - product_tags is empty or None
          - user_value has no entry in similarity_table
          - no tag slug yields a non-zero similarity
    """
    if not product_tags:
        logger.debug(
            f"[Matcher] user_value='{user_value}' → no product tags, match=0.0"
        )
        return 0.0

    user_row: dict[str, float] = similarity_table.get(user_value, {})
    if not user_row:
        logger.debug(
            f"[Matcher] user_value='{user_value}' not found in similarity table, match=0.0"
        )
        return 0.0

    best: float = 0.0
    for tag in product_tags:
        slug: str = tag.get("slug", "")
        if not slug:
            continue
        intensity: float = tag.get("intensity", DEFAULT_INTENSITY)
        sim: float = user_row.get(slug, 0.0)
        score: float = sim * intensity
        logger.debug(
            f"[Matcher] user='{user_value}' × tag='{slug}' "
            f"| sim={sim:.3f} × intensity={intensity:.3f} = {score:.3f}"
        )
        if score > best:
            best = score

    logger.debug(f"[Matcher] user_value='{user_value}' → best match={best:.4f}")
    return best
