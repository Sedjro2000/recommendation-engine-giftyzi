"""
GIFTYZI — Test suite Phase 2.5 (contrat v2 Next.js ↔ FastAPI).

Organisation:
  1. DB connection & données
  2. Schémas stricts (unit — pas de DB)
  3. Hard filters (unit — in-memory)
  4. Soft tag scoring (unit — in-memory + tables de similarité)
  5. API integration (DB + TestClient)

Collection utilisée : products_test (ne touche jamais products).
"""

import logging
from math import inf, nan

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from pymongo import MongoClient
from pymongo.database import Database

from app.api.schemas import FacetWeights, HardFilters, RecommendRequest, SoftTagItem, SoftTags
from app.config.facets import HARD_FACET_SLUGS, OUT_OF_SCOPE_FACET_SLUGS, SIMILARITY_FACETS, SOFT_FACET_SLUGS
from app.config.similarity_loader import get_similarity, load_all_similarity_tables
from app.services.matcher import compute_match
from app.services.recommendation_service import apply_hard_filters, compute_soft_score, rank_products

logger = logging.getLogger(__name__)

TEST_COLLECTION = "products_test"
BUDGET_MAX = 100.0

BASE_PAYLOAD: dict = {
    "status": "active",
    "price": BUDGET_MAX,
}

PUBLIC_RESPONSE_KEYS = {
    "query_interpretation",
    "hard_constraints",
    "soft_preferences",
    "best_matches",
    "related_ideas",
    "relaxations_applied",
    "suggested_reformulations",
    "fallback",
    "meta",
    "debug_info",
}


# ─────────────────────────────────────────────────────────────
# 1. DB CONNECTION & DONNÉES
# ─────────────────────────────────────────────────────────────


def test_db_connection(mongo_client: MongoClient) -> None:
    result = mongo_client.admin.command("ping")
    assert result.get("ok") == 1.0
    logger.debug("[test_db_connection] ping returned ok=1.0 ✓")


def test_insert_and_read_products(
    test_db: Database, inserted_products: list[dict]
) -> None:
    count = test_db[TEST_COLLECTION].count_documents({})
    assert count == 6, f"Expected 6 docs in '{TEST_COLLECTION}', got {count}."
    names = {p["name"] for p in inserted_products}
    expected = {
        "T_Bijou anniversaire",
        "T_Carnet voyage",
        "T_Parfum epuise",
        "T_Montre luxe",
        "T_Agenda inactif",
        "T_Bougie deco",
    }
    assert names == expected
    logger.debug(f"[test_insert_and_read_products] {count} docs verified ✓")


# ─────────────────────────────────────────────────────────────
# 2. SCHÉMAS STRICTS (unit — pas de DB)
# ─────────────────────────────────────────────────────────────


def test_schema_valid_minimal() -> None:
    r = RecommendRequest(**BASE_PAYLOAD)
    assert r.status == "active"
    assert r.price == BUDGET_MAX


def test_schema_valid_full() -> None:
    r = RecommendRequest(
        status="active",
        price=50.0,
        hard_filters={"age_group": ["adulte"], "recipient_gender": ["female"]},
        soft_tags={"event": [{"slug": "anniversaire", "intensity": 0.75}]},
        facet_weights={"event": 1.5},
    )
    assert r.hard_filters.age_group == ["adulte"]
    assert r.soft_tags.event[0].slug == "anniversaire"
    assert r.facet_weights.event == 1.5


def test_schema_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        RecommendRequest(**BASE_PAYLOAD, unknown_field="value")


def test_schema_category_rejected() -> None:
    with pytest.raises(ValidationError):
        RecommendRequest(**BASE_PAYLOAD, category="bijou")


def test_schema_recipient_personality_rejected() -> None:
    with pytest.raises(ValidationError):
        RecommendRequest(**BASE_PAYLOAD, recipient_personality="zen")


@pytest.mark.parametrize(
    "field",
    ["category", "recipient_personality", "keywords", "type", "unknown_field"],
)
def test_schema_bloc7_forbidden_user_fields_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        RecommendRequest(**BASE_PAYLOAD, **{field: "forbidden"})


def test_schema_eventids_rejected() -> None:
    with pytest.raises(ValidationError):
        RecommendRequest(**BASE_PAYLOAD, eventIds=["1", "2"])


def test_schema_metadata_rejected() -> None:
    with pytest.raises(ValidationError):
        RecommendRequest(**BASE_PAYLOAD, metadata={"key": "val"})


def test_schema_iscustomizable_rejected() -> None:
    with pytest.raises(ValidationError):
        RecommendRequest(**BASE_PAYLOAD, isCustomizable=True)


def test_schema_intensity_above_1_rejected() -> None:
    with pytest.raises(ValidationError):
        RecommendRequest(
            **BASE_PAYLOAD,
            soft_tags={"event": [{"slug": "anniversaire", "intensity": 1.5}]},
        )  # 1.5 not in VALID_INTENSITIES


def test_schema_negative_price_rejected() -> None:
    with pytest.raises(ValidationError):
        RecommendRequest(**{**BASE_PAYLOAD, "price": -1.0})


@pytest.mark.parametrize("field", ["product_id", "stock"])
def test_schema_product_projection_fields_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        RecommendRequest(**{**BASE_PAYLOAD, field: "projection-only"})


def test_schema_facet_weight_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        RecommendRequest(**BASE_PAYLOAD, facet_weights={"event": -0.5})


@pytest.mark.parametrize(
    "facet",
    ["event", "relationship", "theme", "gift_benefit"],
)
def test_schema_facet_weight_zero_and_positive_accepted(facet: str) -> None:
    zero = RecommendRequest(**BASE_PAYLOAD, facet_weights={facet: 0})
    positive = RecommendRequest(**BASE_PAYLOAD, facet_weights={facet: 1.75})
    assert getattr(zero.facet_weights, facet) == 0.0
    assert getattr(positive.facet_weights, facet) == 1.75


@pytest.mark.parametrize(
    ("facet", "value"),
    [
        ("event", -0.5),
        ("event", None),
        ("event", nan),
        ("event", inf),
    ],
)
def test_schema_invalid_facet_weight_values_rejected(facet: str, value: float | None) -> None:
    with pytest.raises(ValidationError):
        RecommendRequest(**BASE_PAYLOAD, facet_weights={facet: value})


@pytest.mark.parametrize(
    "facet",
    [
        "category",
        "recipient_personality",
        "age_group",
        "recipient_gender",
        "unknown",
    ],
)
def test_schema_forbidden_facet_weight_keys_rejected(facet: str) -> None:
    with pytest.raises(ValidationError):
        RecommendRequest(**BASE_PAYLOAD, facet_weights={facet: 1.0})


def test_schema_unknown_soft_tag_facet_rejected() -> None:
    with pytest.raises(ValidationError):
        RecommendRequest(
            **BASE_PAYLOAD,
            soft_tags={"category": [{"slug": "bijou", "intensity": 0.5}]},
        )


def test_schema_unknown_hard_filter_field_rejected() -> None:
    with pytest.raises(ValidationError):
        RecommendRequest(**BASE_PAYLOAD, hard_filters={"unknown_field": ["value"]})


def test_schema_unknown_facet_weight_rejected() -> None:
    with pytest.raises(ValidationError):
        RecommendRequest(**BASE_PAYLOAD, facet_weights={"category": 1.0})


# ─────────────────────────────────────────────────────────────
# 2b. SLUG CONTRACT v1 (source de vérité Next.js)
# ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("facet", "slug"),
    [
        ("age_group", "adolescent"),
        ("age_group", "adulte"),
        ("age_group", "bebe"),
        ("age_group", "enfant"),
        ("age_group", "senior"),
        ("recipient_gender", "female"),
        ("recipient_gender", "male"),
        ("recipient_gender", "unisex"),
    ],
)
def test_slug_contract_valid_hard_filter_slug_accepted(
    facet: str,
    slug: str,
) -> None:
    request = RecommendRequest(
        **BASE_PAYLOAD,
        hard_filters={facet: [slug]},
    )
    assert getattr(request.hard_filters, facet) == [slug]


@pytest.mark.parametrize(
    ("facet", "slug"),
    [
        ("event", "saint-valentin"),
        ("relationship", "enfant-relation"),
        ("theme", "eco-friendly"),
        ("gift_benefit", "long-lasting"),
    ],
)
def test_slug_contract_valid_soft_tag_slug_accepted(
    facet: str,
    slug: str,
) -> None:
    request = RecommendRequest(
        **BASE_PAYLOAD,
        soft_tags={facet: [{"slug": slug, "intensity": 1.0}]},
    )
    assert getattr(request.soft_tags, facet)[0].slug == slug


@pytest.mark.parametrize(
    ("payload_update", "message"),
    [
        (
            {"soft_tags": {"event": [{"slug": "not-a-real-slug", "intensity": 1.0}]}},
            "unknown slug",
        ),
        (
            {"soft_tags": {"event": [{"slug": "saint_valentin", "intensity": 1.0}]}},
            "not canonical",
        ),
        (
            {"soft_tags": {"event": [{"slug": "fête-des-mères", "intensity": 1.0}]}},
            "not canonical",
        ),
        (
            {"soft_tags": {"event": [{"slug": "Saint-Valentin", "intensity": 1.0}]}},
            "not canonical",
        ),
        (
            {"soft_tags": {"event": [{"slug": "saint valentin", "intensity": 1.0}]}},
            "not canonical",
        ),
        (
            {"soft_tags": {"event": [{"slug": "fete_des_meres", "intensity": 1.0}]}},
            "not canonical",
        ),
        (
            {"soft_tags": {"theme": [{"slug": "bijoux", "intensity": 1.0}]}},
            "out-of-scope facet 'category'",
        ),
        (
            {"soft_tags": {"theme": [{"slug": "tech-lover", "intensity": 1.0}]}},
            "out-of-scope facet 'recipient_personality'",
        ),
        (
            {"soft_tags": {"theme": [{"slug": "food-category", "intensity": 1.0}]}},
            "out-of-scope facet 'category'",
        ),
        (
            {"soft_tags": {"theme": [{"slug": "creative", "intensity": 1.0}]}},
            "out-of-scope facet 'recipient_personality'",
        ),
        (
            {"soft_tags": {"theme": [{"slug": "mariage", "intensity": 1.0}]}},
            "unknown slug",
        ),
        (
            {"hard_filters": {"age_group": ["adult"]}},
            "unknown slug",
        ),
    ],
)
def test_slug_contract_invalid_payload_rejected(
    payload_update: dict,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        RecommendRequest(**{**BASE_PAYLOAD, **payload_update})


def test_slug_contract_saint_valentin_alias_rejected() -> None:
    with pytest.raises(ValidationError, match="not canonical"):
        RecommendRequest(
            **BASE_PAYLOAD,
            soft_tags={"event": [{"slug": "saint_valentin", "intensity": 1.0}]},
        )


def test_slug_contract_saint_valentin_canonical_accepted() -> None:
    request = RecommendRequest(
        **BASE_PAYLOAD,
        soft_tags={"event": [{"slug": "saint-valentin", "intensity": 1.0}]},
    )
    assert request.soft_tags.event[0].slug == "saint-valentin"


def test_slug_contract_fete_des_meres_alias_rejected() -> None:
    with pytest.raises(ValidationError, match="not canonical"):
        RecommendRequest(
            **BASE_PAYLOAD,
            soft_tags={"event": [{"slug": "fete_des_meres", "intensity": 1.0}]},
        )


def test_slug_contract_fete_des_meres_canonical_accepted() -> None:
    request = RecommendRequest(
        **BASE_PAYLOAD,
        soft_tags={"event": [{"slug": "fete-des-meres", "intensity": 1.0}]},
    )
    assert request.soft_tags.event[0].slug == "fete-des-meres"


@pytest.mark.parametrize(
    "payload_update",
    [
        {"category": "bijoux"},
        {"recipient_personality": "creative"},
        {"soft_tags": {"category": [{"slug": "bijoux", "intensity": 1.0}]}},
        {"soft_tags": {"recipient_personality": [{"slug": "creative", "intensity": 1.0}]}},
        {"soft_tags": {"event": [{"slug": "saint_valentin", "intensity": 1.0}]}},
        {"soft_tags": {"theme": [{"slug": "bijoux", "intensity": 1.0}]}},
    ],
)
def test_slug_contract_endpoint_rejects_invalid_payload(
    payload_update: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", TEST_COLLECTION)
    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/v1/recommend",
        json={**BASE_PAYLOAD, **payload_update},
    )
    assert resp.status_code == 422


# ─────────────────────────────────────────────────────────────
# 3. HARD FILTERS (unit — in-memory)
# ─────────────────────────────────────────────────────────────


def test_hard_filter_stock_zero_excluded(inserted_products: list[dict]) -> None:
    filtered = apply_hard_filters(inserted_products, HardFilters())
    names = {p["name"] for p in filtered}
    assert "T_Parfum epuise" not in names
    for p in filtered:
        assert p["stock"] > 0


def test_hard_filter_empty_passes_non_zero_stock(inserted_products: list[dict]) -> None:
    filtered = apply_hard_filters(inserted_products, HardFilters())
    names = {p["name"] for p in filtered}
    assert "T_Bijou anniversaire" in names
    assert "T_Carnet voyage" in names
    assert "T_Bougie deco" in names


def test_hard_filter_age_group_adulte(inserted_products: list[dict]) -> None:
    filtered = apply_hard_filters(inserted_products, HardFilters(age_group=["adulte"]))
    for p in filtered:
        ag = p.get("age_group", [])
        if isinstance(ag, str):
            ag = [ag]
        assert "adulte" in ag, f"'{p['name']}' ne contient pas 'adulte'"


def test_hard_filter_age_group_adolescent_excludes_adulte_only(inserted_products: list[dict]) -> None:
    filtered = apply_hard_filters(inserted_products, HardFilters(age_group=["adolescent"]))
    names = {p["name"] for p in filtered}
    assert "T_Bijou anniversaire" not in names   # age_group=["adulte"] seulement
    assert "T_Carnet voyage" in names             # age_group=["adulte","adolescent"]
    assert "T_Bougie deco" in names               # age_group=["adolescent","adulte"]


def test_hard_filter_recipient_gender_female(inserted_products: list[dict]) -> None:
    filtered = apply_hard_filters(
        inserted_products, HardFilters(recipient_gender=["female"])
    )
    names = {p["name"] for p in filtered}
    assert "T_Bijou anniversaire" in names    # ["female","unisex"] ✓
    assert "T_Carnet voyage" not in names     # ["unisex"] ✗
    assert "T_Bougie deco" not in names       # ["unisex"] ✗


def test_hard_filter_recipient_gender_female_or_unisex(inserted_products: list[dict]) -> None:
    filtered = apply_hard_filters(
        inserted_products, HardFilters(recipient_gender=["female", "unisex"])
    )
    names = {p["name"] for p in filtered}
    assert "T_Bijou anniversaire" in names
    assert "T_Carnet voyage" in names
    assert "T_Bougie deco" in names


def test_hard_filter_age_and_gender_cumulative(inserted_products: list[dict]) -> None:
    # adolescent + female => aucun produit (Bijou=female/adulte, Carnet=unisex/adolescent)
    filtered = apply_hard_filters(
        inserted_products,
        HardFilters(age_group=["adolescent"], recipient_gender=["female"]),
    )
    assert len(filtered) == 0, f"Attendu 0 produits, got {len(filtered)}"


# ─────────────────────────────────────────────────────────────
# 4. SOFT TAG SCORING (unit — in-memory + tables de similarité)
# ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def sim_tables() -> dict:
    return load_all_similarity_tables()


@pytest.fixture(scope="module")
def bijou_product() -> dict:
    return {
        "name": "T_Bijou anniversaire",
        "stock": 10,
        "tags": {
            "event":        [{"slug": "anniversaire",   "intensity": 1.0},
                             {"slug": "saint-valentin", "intensity": 0.7}],
            "relationship": [{"slug": "partenaire",     "intensity": 0.8},
                             {"slug": "ami",            "intensity": 0.6}],
            "theme":        [{"slug": "romantic",       "intensity": 0.8},
                             {"slug": "luxury",         "intensity": 0.6}],
            "gift_benefit": [{"slug": "emotional",      "intensity": 1.0}],
        },
    }


def test_soft_tag_event_scores(bijou_product: dict, sim_tables: dict) -> None:
    st = SoftTags(event=[SoftTagItem(slug="anniversaire", intensity=1.0)])
    score = compute_soft_score(bijou_product, st, FacetWeights(), sim_tables)
    # sim[anniversaire][anniversaire]=1.0 × prod_intensity=1.0 × user_intensity=1.0 = 1.0
    assert score == pytest.approx(1.0)


def test_soft_tag_relationship_scores(bijou_product: dict, sim_tables: dict) -> None:
    st = SoftTags(relationship=[SoftTagItem(slug="partenaire", intensity=1.0)])
    score = compute_soft_score(bijou_product, st, FacetWeights(), sim_tables)
    # sim[partenaire][partenaire]=1.0 × 0.8 × 1.0 = 0.8
    assert score == pytest.approx(0.8)


def test_soft_tag_theme_scores(bijou_product: dict, sim_tables: dict) -> None:
    st = SoftTags(theme=[SoftTagItem(slug="romantic", intensity=1.0)])
    score = compute_soft_score(bijou_product, st, FacetWeights(), sim_tables)
    # sim[romantic][romantic]=1.0 × 0.8 × 1.0 = 0.8
    assert score == pytest.approx(0.8)


def test_soft_tag_gift_benefit_scores(bijou_product: dict, sim_tables: dict) -> None:
    st = SoftTags(gift_benefit=[SoftTagItem(slug="emotional", intensity=0.75)])
    score = compute_soft_score(bijou_product, st, FacetWeights(), sim_tables)
    # sim[emotional][emotional]=1.0 × prod_intensity=1.0 × user_intensity=0.75 = 0.75
    assert score == pytest.approx(0.75)


def test_similarity_tables_exact_match_is_one(sim_tables: dict) -> None:
    for facet, table in sim_tables.items():
        for slug, row in table.items():
            assert row.get(slug) == pytest.approx(1.0), (
                f"{facet}.{slug} exact match must be 1.0"
            )


def test_similarity_tables_approximate_matches_are_below_one(sim_tables: dict) -> None:
    for facet, table in sim_tables.items():
        for source, row in table.items():
            for target, score in row.items():
                if source == target:
                    continue
                assert score < 1.0, (
                    f"{facet}.{source}->{target} approximate match must be < 1.0"
                )


def _is_canonical_slug(slug: str) -> bool:
    return (
        slug == slug.lower()
        and slug.isascii()
        and " " not in slug
        and "_" not in slug
    )


def test_similarity_tables_only_use_real_soft_facet_slugs(sim_tables: dict) -> None:
    hard_slugs = {slug for slugs in HARD_FACET_SLUGS.values() for slug in slugs}
    out_of_scope_slugs = {
        slug
        for slugs in OUT_OF_SCOPE_FACET_SLUGS.values()
        for slug in slugs
    }

    assert set(sim_tables) == set(SIMILARITY_FACETS)
    for facet, table in sim_tables.items():
        allowed = SOFT_FACET_SLUGS[facet]
        other_soft_slugs = {
            slug
            for other_facet, slugs in SOFT_FACET_SLUGS.items()
            if other_facet != facet
            for slug in slugs
        }
        for source, row in table.items():
            assert source in allowed
            assert source not in hard_slugs
            assert source not in out_of_scope_slugs
            assert source not in other_soft_slugs
            assert _is_canonical_slug(source)
            for target in row:
                assert target in allowed
                assert target not in hard_slugs
                assert target not in out_of_scope_slugs
                assert target not in other_soft_slugs
                assert _is_canonical_slug(target)


def test_similarity_tables_are_symmetric_or_documented(sim_tables: dict) -> None:
    asymmetries = []
    for facet, table in sim_tables.items():
        for source, row in table.items():
            for target, score in row.items():
                if source == target:
                    continue
                reverse_score = table.get(target, {}).get(source)
                if reverse_score != score:
                    asymmetries.append((facet, source, target, score, reverse_score))
    assert asymmetries == []


def test_exact_match_beats_approximate_match_with_same_intensity(sim_tables: dict) -> None:
    event_table = sim_tables["event"]
    exact = compute_match(
        "anniversaire",
        [{"slug": "anniversaire", "intensity": 1.0}],
        event_table,
    )
    approximate = compute_match(
        "anniversaire",
        [{"slug": "juste-faire-plaisir", "intensity": 1.0}],
        event_table,
    )
    assert exact == pytest.approx(1.0)
    assert approximate < 1.0
    assert exact > approximate


def test_unknown_similarity_slug_is_not_silently_scored(sim_tables: dict) -> None:
    event_table = sim_tables["event"]
    with pytest.raises(ValueError, match="unknown similarity slug"):
        compute_match(
            "not-a-real-slug",
            [{"slug": "anniversaire", "intensity": 1.0}],
            event_table,
        )
    with pytest.raises(ValueError, match="unknown similarity slug"):
        compute_match(
            "anniversaire",
            [{"slug": "not-a-real-slug", "intensity": 1.0}],
            event_table,
        )
    with pytest.raises(ValueError, match="unknown similarity slug"):
        get_similarity("event", "anniversaire", "not-a-real-slug")


def test_soft_tags_absent_score_zero(bijou_product: dict, sim_tables: dict) -> None:
    score = compute_soft_score(bijou_product, SoftTags(), FacetWeights(), sim_tables)
    assert score == 0.0


def test_product_without_tags_scores_zero(sim_tables: dict) -> None:
    product = {"name": "Sans tags", "stock": 1, "tags": {}}
    st = SoftTags(event=[SoftTagItem(slug="anniversaire", intensity=1.0)])
    assert compute_soft_score(product, st, FacetWeights(), sim_tables) == 0.0


def test_intensity_low_vs_high(bijou_product: dict, sim_tables: dict) -> None:
    fw = FacetWeights()
    st_low  = SoftTags(event=[SoftTagItem(slug="anniversaire", intensity=0.25)])
    st_high = SoftTags(event=[SoftTagItem(slug="anniversaire", intensity=1.0)])
    score_low  = compute_soft_score(bijou_product, st_low,  fw, sim_tables)
    score_high = compute_soft_score(bijou_product, st_high, fw, sim_tables)
    assert score_low < score_high
    assert score_low  == pytest.approx(0.25)  # minimum valid intensity
    assert score_high == pytest.approx(1.0)   # maximum valid intensity


def test_facet_weights_low_vs_high(bijou_product: dict, sim_tables: dict) -> None:
    st = SoftTags(event=[SoftTagItem(slug="anniversaire", intensity=1.0)])
    score_low  = compute_soft_score(bijou_product, st, FacetWeights(event=0.5), sim_tables)
    score_high = compute_soft_score(bijou_product, st, FacetWeights(event=2.0), sim_tables)
    assert score_low < score_high
    assert score_low  == pytest.approx(0.5)
    assert score_high == pytest.approx(2.0)


@pytest.mark.parametrize(
    ("facet", "slug", "base_score"),
    [
        ("event", "anniversaire", 1.0),
        ("relationship", "partenaire", 0.8),
        ("theme", "romantic", 0.8),
        ("gift_benefit", "emotional", 1.0),
    ],
)
def test_each_facet_weight_influences_score(
    bijou_product: dict,
    sim_tables: dict,
    facet: str,
    slug: str,
    base_score: float,
) -> None:
    soft_tags = SoftTags(**{facet: [SoftTagItem(slug=slug, intensity=1.0)]})
    low = compute_soft_score(
        bijou_product,
        soft_tags,
        FacetWeights(**{facet: 0.5}),
        sim_tables,
    )
    high = compute_soft_score(
        bijou_product,
        soft_tags,
        FacetWeights(**{facet: 2.0}),
        sim_tables,
    )
    assert low == pytest.approx(base_score * 0.5)
    assert high == pytest.approx(base_score * 2.0)
    assert low < high


def test_facet_weight_zero_silences_facet(bijou_product: dict, sim_tables: dict) -> None:
    st = SoftTags(event=[SoftTagItem(slug="anniversaire", intensity=1.0)])
    score = compute_soft_score(bijou_product, st, FacetWeights(event=0.0), sim_tables)
    assert score == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("facet", "slug"),
    [
        ("event", "anniversaire"),
        ("relationship", "partenaire"),
        ("theme", "romantic"),
        ("gift_benefit", "emotional"),
    ],
)
def test_facet_weight_zero_silences_each_facet(
    bijou_product: dict,
    sim_tables: dict,
    facet: str,
    slug: str,
) -> None:
    soft_tags = SoftTags(**{facet: [SoftTagItem(slug=slug, intensity=1.0)]})
    score = compute_soft_score(
        bijou_product,
        soft_tags,
        FacetWeights(**{facet: 0.0}),
        sim_tables,
    )
    assert score == pytest.approx(0.0)


def test_facet_weight_absent_equals_default_one(bijou_product: dict, sim_tables: dict) -> None:
    st = SoftTags(event=[SoftTagItem(slug="anniversaire", intensity=1.0)])
    score_absent = compute_soft_score(bijou_product, st, FacetWeights(),          sim_tables)
    score_one    = compute_soft_score(bijou_product, st, FacetWeights(event=1.0), sim_tables)
    assert score_absent == pytest.approx(score_one)


@pytest.mark.parametrize(
    ("facet", "slug"),
    [
        ("event", "anniversaire"),
        ("relationship", "partenaire"),
        ("theme", "romantic"),
        ("gift_benefit", "emotional"),
    ],
)
def test_facet_weight_absent_equals_neutral_one_for_each_facet(
    bijou_product: dict,
    sim_tables: dict,
    facet: str,
    slug: str,
) -> None:
    soft_tags = SoftTags(**{facet: [SoftTagItem(slug=slug, intensity=1.0)]})
    absent = compute_soft_score(bijou_product, soft_tags, FacetWeights(), sim_tables)
    explicit_one = compute_soft_score(
        bijou_product,
        soft_tags,
        FacetWeights(**{facet: 1.0}),
        sim_tables,
    )
    assert absent == pytest.approx(explicit_one)


def test_no_hardcoded_weight_changes_score(bijou_product: dict, sim_tables: dict) -> None:
    soft_tags = SoftTags(
        event=[SoftTagItem(slug="anniversaire", intensity=1.0)],
        relationship=[SoftTagItem(slug="partenaire", intensity=1.0)],
        theme=[SoftTagItem(slug="romantic", intensity=1.0)],
        gift_benefit=[SoftTagItem(slug="emotional", intensity=1.0)],
    )
    score = compute_soft_score(bijou_product, soft_tags, FacetWeights(), sim_tables)
    assert score == pytest.approx(1.0 + 0.8 + 0.8 + 1.0)


def test_stable_sort_equal_scores(sim_tables: dict) -> None:
    st = SoftTags(event=[SoftTagItem(slug="anniversaire", intensity=1.0)])
    fw = FacetWeights()
    products = [
        {"_id": "zzz", "name": "Z", "stock": 1, "tags": {"event": [{"slug": "anniversaire", "intensity": 1.0}]}},
        {"_id": "aaa", "name": "A", "stock": 1, "tags": {"event": [{"slug": "anniversaire", "intensity": 1.0}]}},
        {"_id": "mmm", "name": "M", "stock": 1, "tags": {"event": [{"slug": "anniversaire", "intensity": 1.0}]}},
    ]
    r1 = rank_products(products, st, fw, sim_tables)
    r2 = rank_products(products, st, fw, sim_tables)
    assert [p["_id"] for p in r1] == [p["_id"] for p in r2]
    assert [p["_id"] for p in r1] == ["aaa", "mmm", "zzz"]  # _id asc tie-breaker


def test_rank_descending_order(bijou_product: dict, sim_tables: dict) -> None:
    no_tags = {"name": "Sans tags", "stock": 1, "tags": {}}
    carnet  = {
        "name": "T_Carnet", "stock": 1,
        "tags": {"event": [{"slug": "juste-faire-plaisir", "intensity": 0.8}]},
    }
    st = SoftTags(event=[SoftTagItem(slug="anniversaire", intensity=1.0)])
    ranked = rank_products([no_tags, bijou_product, carnet], st, FacetWeights(), sim_tables)
    scores = [p["_score"] for p in ranked]
    assert scores == sorted(scores, reverse=True)
    assert ranked[0]["name"] == "T_Bijou anniversaire"


@pytest.mark.parametrize(
    ("facet", "requested_slug", "winning_slug", "losing_slug"),
    [
        ("event", "anniversaire", "anniversaire", "noel"),
        ("relationship", "partenaire", "partenaire", "ami"),
        ("theme", "romantic", "romantic", "tech"),
        ("gift_benefit", "emotional", "emotional", "useful"),
    ],
)
def test_bloc7_each_soft_signal_changes_ranking(
    sim_tables: dict,
    facet: str,
    requested_slug: str,
    winning_slug: str,
    losing_slug: str,
) -> None:
    products = [
        {
            "_id": "loser",
            "name": f"Produit {losing_slug}",
            "stock": 1,
            "tags": {facet: [{"slug": losing_slug, "intensity": 1.0}]},
        },
        {
            "_id": "winner",
            "name": f"Produit {winning_slug}",
            "stock": 1,
            "tags": {facet: [{"slug": winning_slug, "intensity": 1.0}]},
        },
    ]
    soft_tags = SoftTags(
        **{facet: [SoftTagItem(slug=requested_slug, intensity=1.0)]}
    )

    ranked = rank_products(products, soft_tags, FacetWeights(), sim_tables)

    assert ranked[0]["_id"] == "winner"
    assert ranked[0]["_score"] > ranked[1]["_score"]


# ─────────────────────────────────────────────────────────────
# 5. INTENSITY POLICY v1
# ─────────────────────────────────────────────────────────────


def test_intensity_policy_rejects_free_float() -> None:
    for bad in [0.0, 0.1, 0.3, 0.6, 0.9, 0.99]:
        with pytest.raises(ValidationError, match="intensity"):
            RecommendRequest(
                **BASE_PAYLOAD,
                soft_tags={"event": [{"slug": "anniversaire", "intensity": bad}]},
            )


def test_intensity_policy_rejects_null() -> None:
    with pytest.raises(ValidationError):
        SoftTagItem(slug="anniversaire", intensity=None)


def test_intensity_policy_rejects_absent() -> None:
    with pytest.raises(ValidationError):
        SoftTagItem(slug="anniversaire")


def test_intensity_policy_accepts_all_valid_values() -> None:
    for v in [0.25, 0.5, 0.75, 1.0]:
        item = SoftTagItem(slug="anniversaire", intensity=v)
        assert item.intensity == v


def test_intensity_policy_hard_filters_no_intensity() -> None:
    from app.api.schemas import HardFilters
    hf = HardFilters(age_group=["adulte"], recipient_gender=["female"])
    assert not hasattr(hf, "intensity")
    with pytest.raises(ValidationError):
        HardFilters(age_group=["adulte"], intensity=0.5)


def test_intensity_policy_scoring_proportional(bijou_product: dict, sim_tables: dict) -> None:
    fw = FacetWeights()
    scores = {}
    for v in [0.25, 0.5, 0.75, 1.0]:
        st = SoftTags(event=[SoftTagItem(slug="anniversaire", intensity=v)])
        scores[v] = compute_soft_score(bijou_product, st, fw, sim_tables)
    assert scores[0.25] == pytest.approx(0.25)
    assert scores[0.5]  == pytest.approx(0.5)
    assert scores[0.75] == pytest.approx(0.75)
    assert scores[1.0]  == pytest.approx(1.0)
    assert scores[0.25] < scores[0.5] < scores[0.75] < scores[1.0]


def test_intensity_policy_factor_4x(bijou_product: dict, sim_tables: dict) -> None:
    fw = FacetWeights()
    st_min = SoftTags(event=[SoftTagItem(slug="anniversaire", intensity=0.25)])
    st_max = SoftTags(event=[SoftTagItem(slug="anniversaire", intensity=1.0)])
    s_min = compute_soft_score(bijou_product, st_min, fw, sim_tables)
    s_max = compute_soft_score(bijou_product, st_max, fw, sim_tables)
    assert s_max / s_min == pytest.approx(4.0)


# ─────────────────────────────────────────────────────────────
# 6. API INTEGRATION (DB + TestClient)
# ─────────────────────────────────────────────────────────────


def _assert_public_response_shape(body: dict) -> None:
    assert set(body) == PUBLIC_RESPONSE_KEYS
    assert isinstance(body["query_interpretation"], dict)
    assert isinstance(body["hard_constraints"], dict)
    assert isinstance(body["soft_preferences"], dict)
    assert isinstance(body["best_matches"], list)
    assert isinstance(body["related_ideas"], list)
    assert isinstance(body["relaxations_applied"], list)
    assert isinstance(body["suggested_reformulations"], list)
    assert isinstance(body["meta"], dict)
    assert isinstance(body["debug_info"], dict)
    assert body["meta"]["contract_version"] == "recommendation_public_v1"
    assert body["meta"]["result_count"] == len(body["best_matches"])
    assert body["meta"]["limit"] == 10
    assert body["debug_info"]["stock_filter"] == "stock > 0"
    assert body["debug_info"]["exact_match_score"] == 1.0


def test_recommend_endpoint_valid(
    inserted_products: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", TEST_COLLECTION)
    from app.main import app
    with TestClient(app) as client:
        resp = client.post("/api/v1/recommend", json=BASE_PAYLOAD)
    assert resp.status_code == 200
    body = resp.json()
    _assert_public_response_shape(body)
    assert len(body["best_matches"]) <= 10
    assert body["fallback"] is None
    assert body["hard_constraints"]["budget_max"] == BUDGET_MAX
    assert body["hard_constraints"]["availability"] == "in_stock"
    assert body["query_interpretation"]["detected_signals"]["budget_max"] == BUDGET_MAX


def test_unknown_field_rejected_by_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", TEST_COLLECTION)
    from app.main import app
    with TestClient(app) as client:
        resp = client.post("/api/v1/recommend", json={**BASE_PAYLOAD, "category": "bijou"})
    assert resp.status_code == 422


@pytest.mark.parametrize("field", ["product_id", "stock", "unknown_field"])
def test_public_request_forbidden_fields_rejected_by_endpoint(
    field: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", TEST_COLLECTION)
    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/v1/recommend",
        json={**BASE_PAYLOAD, field: "forbidden"},
    )
    assert resp.status_code == 422


def test_status_required_by_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", TEST_COLLECTION)
    from app.main import app

    payload = {k: v for k, v in BASE_PAYLOAD.items() if k != "status"}
    client = TestClient(app)
    resp = client.post("/api/v1/recommend", json=payload)
    assert resp.status_code == 422


def test_price_required_by_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", TEST_COLLECTION)
    from app.main import app

    payload = {k: v for k, v in BASE_PAYLOAD.items() if k != "price"}
    client = TestClient(app)
    resp = client.post("/api/v1/recommend", json=payload)
    assert resp.status_code == 422


def test_public_response_fallback_when_no_matches(
    inserted_products: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", TEST_COLLECTION)
    from app.main import app

    with TestClient(app) as client:
        resp = client.post("/api/v1/recommend", json={**BASE_PAYLOAD, "price": 1.0})
    assert resp.status_code == 200
    body = resp.json()
    _assert_public_response_shape(body)
    assert body["best_matches"] == []
    assert body["fallback"] == {
        "reason": "no_matches",
        "message": "Aucun produit ne correspond aux contraintes actuelles.",
    }
    assert body["meta"]["result_count"] == 0


def test_stock_zero_excluded_endpoint(
    inserted_products: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", TEST_COLLECTION)
    from app.main import app
    with TestClient(app) as client:
        resp = client.post("/api/v1/recommend", json=BASE_PAYLOAD)
    assert resp.status_code == 200
    matches = resp.json()["best_matches"]
    assert all(m["stock"] > 0 for m in matches)
    assert not any(m["name"] == "T_Parfum epuise" for m in matches)


def test_status_inactive_excluded_endpoint(
    inserted_products: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", TEST_COLLECTION)
    from app.main import app
    with TestClient(app) as client:
        resp = client.post("/api/v1/recommend", json=BASE_PAYLOAD)
    assert resp.status_code == 200
    matches = resp.json()["best_matches"]
    assert all(m["status"] == "active" for m in matches)
    assert not any(m["name"] == "T_Agenda inactif" for m in matches)


def test_price_above_budget_excluded_endpoint(
    inserted_products: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", TEST_COLLECTION)
    from app.main import app
    with TestClient(app) as client:
        resp = client.post("/api/v1/recommend", json=BASE_PAYLOAD)
    assert resp.status_code == 200
    matches = resp.json()["best_matches"]
    assert all(m["price"] <= BUDGET_MAX for m in matches)
    assert not any(m["name"] == "T_Montre luxe" for m in matches)


def test_age_group_hard_filter_endpoint(
    inserted_products: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", TEST_COLLECTION)
    from app.main import app
    payload = {**BASE_PAYLOAD, "hard_filters": {"age_group": ["adolescent"]}}
    with TestClient(app) as client:
        resp = client.post("/api/v1/recommend", json=payload)
    assert resp.status_code == 200
    names = [m["name"] for m in resp.json()["best_matches"]]
    assert "T_Bijou anniversaire" not in names   # adulte seulement → exclu
    assert "T_Carnet voyage" in names             # ["adulte","adolescent"] → passe
    assert "T_Bougie deco" in names               # ["adolescent","adulte"] → passe


def test_recipient_gender_hard_filter_endpoint(
    inserted_products: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", TEST_COLLECTION)
    from app.main import app
    payload = {**BASE_PAYLOAD, "hard_filters": {"recipient_gender": ["female"]}}
    with TestClient(app) as client:
        resp = client.post("/api/v1/recommend", json=payload)
    assert resp.status_code == 200
    names = [m["name"] for m in resp.json()["best_matches"]]
    assert "T_Bijou anniversaire" in names    # ["female","unisex"] → passe
    assert "T_Carnet voyage" not in names     # ["unisex"] → exclu
    assert "T_Bougie deco" not in names       # ["unisex"] → exclu


def test_event_soft_tag_ranking_endpoint(
    inserted_products: list[dict], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRODUCTS_COLLECTION", TEST_COLLECTION)
    from app.main import app
    payload = {
        **BASE_PAYLOAD,
        "soft_tags": {"event": [{"slug": "anniversaire", "intensity": 1.0}]},
    }
    with TestClient(app) as client:
        resp = client.post("/api/v1/recommend", json=payload)
    assert resp.status_code == 200
    matches = resp.json()["best_matches"]
    assert matches[0]["name"] == "T_Bijou anniversaire"   # exact match anniversaire
    scores = [m["_score"] for m in matches]
    assert scores == sorted(scores, reverse=True)
    assert "_score" in matches[0]
    assert "_explanation" in matches[0]
    assert "matched_hard_filters" in matches[0]["_explanation"]
    assert "matched_soft_tags" in matches[0]["_explanation"]
    assert "score_breakdown" in matches[0]["_explanation"]

    logger.debug(
        f"[test_recommend_endpoint] {len(matches)} matches returned, "
        f"all hard constraints respected ✓"
    )
