import json
import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_SIMILARITY_DIR = Path(__file__).parent / "similarity"
_KNOWN_FACETS = ("event", "relationship", "theme", "gift_benefit")


def load_similarity_table(facet: str) -> dict[str, dict[str, float]]:
    """Load a similarity table JSON for the given facet name.

    Returns an empty dict if the file does not exist, allowing the rest of
    the pipeline to degrade gracefully with a score of 0.
    """
    path = _SIMILARITY_DIR / f"{facet}.json"
    if not path.exists():
        logger.warning(f"[SimilarityLoader] Table not found for facet '{facet}': {path}")
        return {}
    with open(path, "r", encoding="utf-8") as f:
        table: dict[str, dict[str, float]] = json.load(f)
    logger.debug(f"[SimilarityLoader] Loaded '{facet}' table: {len(table)} entries.")
    return table


@lru_cache(maxsize=None)
def load_all_similarity_tables() -> dict[str, dict[str, dict[str, float]]]:
    """Load and cache all known similarity tables at first call."""
    tables: dict[str, dict[str, dict[str, float]]] = {}
    for facet in _KNOWN_FACETS:
        tables[facet] = load_similarity_table(facet)
    logger.info(
        f"[SimilarityLoader] Tables loaded: "
        + ", ".join(f"{k}({len(v)} keys)" for k, v in tables.items())
    )
    return tables


def get_similarity(
    facet: str,
    user_value: str,
    product_tag: str,
) -> float:
    """Return similarity(user_value, product_tag) for a given facet.

    Returns 0.0 if the facet, user_value, or product_tag is not in the table.
    """
    tables = load_all_similarity_tables()
    return tables.get(facet, {}).get(user_value, {}).get(product_tag, 0.0)
