from scripts.backfill_projection_slugs import audit_docs

PROJECTION_COLLECTION = "ProductRecommendationProjection"


def test_product_recommendation_projection_uses_official_slugs(test_db) -> None:
    docs = list(test_db[PROJECTION_COLLECTION].find({}))
    audit = audit_docs(docs)

    assert audit["invalids"] == [], (
        "ProductRecommendationProjection contains invalid recommendation slugs: "
        f"{audit['invalids']}"
    )
