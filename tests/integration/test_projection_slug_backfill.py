from scripts.backfill_projection_slugs import (
    audit_docs,
    build_updates,
    normalize_projection_doc,
)


def test_projection_slug_mapping_replaces_known_invalid_slugs() -> None:
    doc = {
        "_id": "projection-1",
        "hard_filters": {},
        "soft_tags": {
            "event": [
                {"slug": "juste_faire_plaisir", "intensity": 0.7},
                {"slug": "fete_des_meres", "intensity": 1.0},
                {"slug": "fete_des_peres", "intensity": 0.5},
            ],
            "relationship": [{"slug": "un_proche", "intensity": 0.8}],
        },
    }

    normalized, changes = normalize_projection_doc(doc)

    assert normalized["soft_tags"]["event"] == [
        {"slug": "juste-faire-plaisir", "intensity": 0.7},
        {"slug": "fete-des-meres", "intensity": 1.0},
        {"slug": "fete-des-peres", "intensity": 0.5},
    ]
    assert normalized["soft_tags"]["relationship"] == [
        {"slug": "un-proche", "intensity": 0.8}
    ]
    assert changes == [
        {"facet": "event", "from": "juste_faire_plaisir", "to": "juste-faire-plaisir"},
        {"facet": "event", "from": "fete_des_meres", "to": "fete-des-meres"},
        {"facet": "event", "from": "fete_des_peres", "to": "fete-des-peres"},
        {"facet": "relationship", "from": "un_proche", "to": "un-proche"},
    ]


def test_projection_slug_backfill_deduplicates_after_replacement() -> None:
    doc = {
        "_id": "projection-2",
        "hard_filters": {
            "age_group": ["adulte", "adulte"],
            "recipient_gender": ["female"],
        },
        "soft_tags": {
            "event": [
                {"slug": "juste_faire_plaisir", "intensity": 0.4},
                {"slug": "juste-faire-plaisir", "intensity": 0.9},
            ],
            "relationship": [],
            "theme": [],
            "gift_benefit": [],
        },
    }

    normalized, _ = normalize_projection_doc(doc)

    assert normalized["hard_filters"]["age_group"] == ["adulte"]
    assert normalized["soft_tags"]["event"] == [
        {"slug": "juste-faire-plaisir", "intensity": 0.9}
    ]


def test_projection_slug_backfill_preserves_already_valid_slugs() -> None:
    doc = {
        "_id": "projection-3",
        "hard_filters": {
            "age_group": ["adulte"],
            "recipient_gender": ["unisex"],
        },
        "soft_tags": {
            "event": [{"slug": "anniversaire", "intensity": 1.0}],
            "relationship": [{"slug": "ami", "intensity": 1.0}],
            "theme": [{"slug": "tech", "intensity": 1.0}],
            "gift_benefit": [{"slug": "useful", "intensity": 1.0}],
        },
    }

    normalized, changes = normalize_projection_doc(doc)

    assert normalized == doc
    assert changes == []
    assert build_updates([doc]) == []


def test_unknown_unmapped_slug_is_reported_but_not_invented() -> None:
    doc = {
        "_id": "projection-4",
        "name": "Projection with unknown slug",
        "hard_filters": {},
        "soft_tags": {
            "event": [{"slug": "unknown_event_slug", "intensity": 1.0}],
        },
    }

    normalized, changes = normalize_projection_doc(doc)
    audit = audit_docs([normalized])

    assert changes == []
    assert normalized["soft_tags"]["event"] == [
        {"slug": "unknown_event_slug", "intensity": 1.0}
    ]
    assert audit["invalids"] == [
        {
            "facet": "event",
            "slug": "unknown_event_slug",
            "count": 1,
            "proposed_fix": None,
            "examples": [
                {
                    "_id": "projection-4",
                    "name": "Projection with unknown slug",
                    "proposed_fix": None,
                }
            ],
        }
    ]
