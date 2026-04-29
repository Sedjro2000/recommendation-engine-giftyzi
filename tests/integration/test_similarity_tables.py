import json
from pathlib import Path
from typing import Any

import pytest

from app.config.facets import SOFT_FACET_SLUGS

SIMILARITY_DIR = Path(__file__).parents[2] / "app" / "config" / "similarity"

EXPECTED_THEME_KEYS = {
    "romantic",
    "luxury",
    "funny",
    "tech",
    "wellness",
    "travel",
    "handmade",
    "minimalist",
    "traditional",
    "decorative",
    "art",
    "beauty",
    "eco-friendly",
    "experience",
    "fashion",
    "modern",
    "personalized",
    "practical",
    "food",
    "drink",
}

EXPECTED_GIFT_BENEFIT_KEYS = {
    "emotional",
    "memorable",
    "useful",
    "long-lasting",
    "entertaining",
    "experiential",
    "decorative-benefit",
    "collectible",
    "educational",
    "surprising",
}


def _load_table(facet: str) -> dict[str, dict[str, Any]]:
    path = SIMILARITY_DIR / f"{facet}.json"
    assert path.exists(), f"Missing similarity table: {path}"
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    assert isinstance(data, dict)
    return data


@pytest.mark.parametrize(
    ("facet", "expected_keys"),
    [
        ("theme", EXPECTED_THEME_KEYS),
        ("gift_benefit", EXPECTED_GIFT_BENEFIT_KEYS),
    ],
)
def test_similarity_table_contains_expected_contract_keys(
    facet: str,
    expected_keys: set[str],
) -> None:
    table = _load_table(facet)

    assert expected_keys <= set(table)
    assert expected_keys == set(SOFT_FACET_SLUGS[facet])


@pytest.mark.parametrize("facet", ["theme", "gift_benefit"])
def test_similarity_scores_are_numeric_and_bounded(facet: str) -> None:
    table = _load_table(facet)

    for source_slug, row in table.items():
        assert isinstance(row, dict), f"{facet}.{source_slug} must be an object"
        assert row.get(source_slug) == 1.0

        for target_slug, score in row.items():
            assert isinstance(score, int | float), (
                f"{facet}.{source_slug}.{target_slug} must be numeric"
            )
            assert 0 <= score <= 1, (
                f"{facet}.{source_slug}.{target_slug} must be between 0 and 1"
            )


@pytest.mark.parametrize("facet", ["theme", "gift_benefit"])
def test_similarity_table_only_references_known_soft_tags(facet: str) -> None:
    table = _load_table(facet)
    allowed = SOFT_FACET_SLUGS[facet]

    assert set(table) <= allowed
    for source_slug, row in table.items():
        assert set(row) <= allowed, (
            f"{facet}.{source_slug} references unknown tags: {set(row) - allowed}"
        )
