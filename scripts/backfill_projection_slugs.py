from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

from app.config.facets import HARD_FACET_SLUGS, SOFT_FACET_SLUGS

COLLECTION_NAME = "ProductRecommendationProjection"

SLUG_REPLACEMENTS: dict[str, dict[str, str]] = {
    "event": {
        "juste_faire_plaisir": "juste-faire-plaisir",
        "fete_des_meres": "fete-des-meres",
        "fete_des_peres": "fete-des-peres",
    },
    "relationship": {
        "un_proche": "un-proche",
    },
}

OFFICIAL_SLUGS: dict[str, frozenset[str]] = {
    **HARD_FACET_SLUGS,
    **SOFT_FACET_SLUGS,
}

HARD_FACETS = ("age_group", "recipient_gender")
SOFT_FACETS = ("event", "relationship", "theme", "gift_benefit")


def normalize_hard_slugs(
    values: list[Any],
    facet: str,
) -> tuple[list[Any], list[dict[str, str]]]:
    replacements = SLUG_REPLACEMENTS.get(facet, {})
    normalized: list[Any] = []
    seen: set[Any] = set()
    changes: list[dict[str, str]] = []

    for value in values:
        new_value = replacements.get(value, value)
        if new_value != value:
            changes.append({"facet": facet, "from": value, "to": new_value})
        if new_value not in seen:
            normalized.append(new_value)
            seen.add(new_value)

    return normalized, changes


def normalize_soft_tags(
    values: list[Any],
    facet: str,
) -> tuple[list[Any], list[dict[str, str]]]:
    replacements = SLUG_REPLACEMENTS.get(facet, {})
    by_slug: dict[str, Any] = {}
    passthrough: list[Any] = []
    changes: list[dict[str, str]] = []

    for item in values:
        if not isinstance(item, dict):
            passthrough.append(item)
            continue

        original_slug = item.get("slug")
        new_slug = replacements.get(original_slug, original_slug)
        if new_slug != original_slug:
            changes.append({"facet": facet, "from": original_slug, "to": new_slug})

        normalized_item = {**item, "slug": new_slug}
        if not isinstance(new_slug, str):
            passthrough.append(normalized_item)
            continue

        existing = by_slug.get(new_slug)
        if existing is None:
            by_slug[new_slug] = normalized_item
            continue

        current_intensity = normalized_item.get("intensity")
        existing_intensity = existing.get("intensity")
        if isinstance(current_intensity, int | float) and isinstance(
            existing_intensity, int | float
        ):
            existing["intensity"] = max(existing_intensity, current_intensity)

    return [*by_slug.values(), *passthrough], changes


def normalize_projection_doc(doc: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    normalized = deepcopy(doc)
    changes: list[dict[str, str]] = []

    hard_filters = normalized.get("hard_filters")
    if isinstance(hard_filters, dict):
        for facet in HARD_FACETS:
            values = hard_filters.get(facet)
            if isinstance(values, list):
                new_values, facet_changes = normalize_hard_slugs(values, facet)
                hard_filters[facet] = new_values
                changes.extend(facet_changes)

    soft_tags = normalized.get("soft_tags")
    if isinstance(soft_tags, dict):
        for facet in SOFT_FACETS:
            values = soft_tags.get(facet)
            if isinstance(values, list):
                new_values, facet_changes = normalize_soft_tags(values, facet)
                soft_tags[facet] = new_values
                changes.extend(facet_changes)

    return normalized, changes


def iter_projection_slugs(doc: dict[str, Any]) -> list[tuple[str, Any]]:
    found: list[tuple[str, Any]] = []

    hard_filters = doc.get("hard_filters") or {}
    if isinstance(hard_filters, dict):
        for facet in HARD_FACETS:
            values = hard_filters.get(facet) or []
            if isinstance(values, list):
                found.extend((facet, value) for value in values)

    soft_tags = doc.get("soft_tags") or {}
    if isinstance(soft_tags, dict):
        for facet in SOFT_FACETS:
            values = soft_tags.get(facet) or []
            if isinstance(values, list):
                for item in values:
                    slug = item.get("slug") if isinstance(item, dict) else item
                    found.append((facet, slug))

    return found


def audit_docs(docs: list[dict[str, Any]]) -> dict[str, Any]:
    invalid_counts: Counter[tuple[str, Any]] = Counter()
    examples: dict[tuple[str, Any], list[dict[str, Any]]] = defaultdict(list)

    for doc in docs:
        for facet, slug in iter_projection_slugs(doc):
            if slug not in OFFICIAL_SLUGS[facet]:
                key = (facet, slug)
                invalid_counts[key] += 1
                if len(examples[key]) < 5:
                    examples[key].append(
                        {
                            "_id": str(doc.get("_id")),
                            "name": doc.get("name"),
                            "proposed_fix": SLUG_REPLACEMENTS.get(facet, {}).get(slug),
                        }
                    )

    return {
        "invalids": [
            {
                "facet": facet,
                "slug": slug,
                "count": count,
                "proposed_fix": SLUG_REPLACEMENTS.get(facet, {}).get(slug),
                "examples": examples[(facet, slug)],
            }
            for (facet, slug), count in sorted(
                invalid_counts.items(),
                key=lambda item: (item[0][0], str(item[0][1])),
            )
        ]
    }


def build_updates(docs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    updates: list[dict[str, Any]] = []
    for doc in docs:
        normalized, changes = normalize_projection_doc(doc)
        if not changes:
            continue
        updates.append(
            {
                "_id": doc["_id"],
                "changes": changes,
                "set": {
                    "hard_filters": normalized.get("hard_filters"),
                    "soft_tags": normalized.get("soft_tags"),
                },
            }
        )
    return updates


def load_database() -> Database:
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env")
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set.")

    client = MongoClient(database_url, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    return client.get_default_database()


def ensure_not_production(db_name: str) -> None:
    lowered = db_name.lower()
    if "prod" in lowered and "staging" not in lowered:
        raise RuntimeError(
            f"Refusing to run against production-like database '{db_name}'."
        )


def run_backfill(db: Database, apply: bool) -> dict[str, Any]:
    ensure_not_production(db.name)

    collection = db[COLLECTION_NAME]
    docs = list(collection.find({}))
    before = audit_docs(docs)
    updates = build_updates(docs)

    modified_count = 0
    if apply:
        for update in updates:
            result = collection.update_one(
                {"_id": update["_id"]},
                {"$set": update["set"]},
            )
            modified_count += result.modified_count

    after: dict[str, Any] | None = None
    if apply:
        after = audit_docs(list(collection.find({})))

    return {
        "database": db.name,
        "collection": COLLECTION_NAME,
        "mode": "apply" if apply else "dry-run",
        "documents_scanned": len(docs),
        "documents_with_known_replacements": len(updates),
        "documents_modified": modified_count,
        "before": before,
        "after": after,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit and backfill invalid slugs in ProductRecommendationProjection."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes. Default is dry-run only.",
    )
    args = parser.parse_args()

    report = run_backfill(load_database(), apply=args.apply)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
