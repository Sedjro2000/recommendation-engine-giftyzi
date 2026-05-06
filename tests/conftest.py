"""Test fixtures for GIFTYZI."""

import logging
from typing import Any, Generator

import pytest
from fastapi.testclient import TestClient

logger = logging.getLogger(__name__)

TEST_COLLECTION = "products_test"

TEST_PRODUCTS = [
    {
        "name": "T_Bijou anniversaire",
        "price": 30.0,
        "stock": 10,
        "status": "active",
        "age_group": ["adulte"],
        "recipient_gender": ["female", "unisex"],
        "occasion_score": {"anniversaire": 0.95, "noel": 0.60},
        "tags": {
            "event":        [{"slug": "anniversaire", "intensity": 1.0}, {"slug": "saint-valentin", "intensity": 0.7}],
            "relationship": [{"slug": "partenaire",   "intensity": 0.8}, {"slug": "ami", "intensity": 0.6}],
            "theme":        [{"slug": "romantic",     "intensity": 0.8}, {"slug": "luxury", "intensity": 0.6}],
            "gift_benefit": [{"slug": "emotional",    "intensity": 1.0}],
        },
    },
    {
        "name": "T_Carnet voyage",
        "price": 20.0,
        "stock": 5,
        "status": "active",
        "age_group": ["adulte", "adolescent"],
        "recipient_gender": ["unisex"],
        "occasion_score": {"anniversaire": 0.30, "noel": 0.40},
        "tags": {
            "event": [{"slug": "juste-faire-plaisir", "intensity": 0.8}],
            "theme": [{"slug": "travel", "intensity": 1.0}],
        },
    },
    {
        "name": "T_Parfum epuise",
        "price": 45.0,
        "stock": 0,
        "status": "active",
        "age_group": ["adulte"],
        "recipient_gender": ["female"],
        "occasion_score": {"anniversaire": 0.90},
        "tags": {
            "event": [{"slug": "anniversaire", "intensity": 0.8}],
            "theme": [{"slug": "wellness",     "intensity": 0.9}],
        },
    },
    {
        "name": "T_Montre luxe",
        "price": 200.0,
        "stock": 8,
        "status": "active",
        "age_group": ["adulte"],
        "recipient_gender": ["male"],
        "occasion_score": {"anniversaire": 0.85},
        "tags": {
            "event": [{"slug": "anniversaire", "intensity": 0.9}],
            "theme": [{"slug": "luxury",       "intensity": 1.0}],
        },
    },
    {
        "name": "T_Agenda inactif",
        "price": 25.0,
        "stock": 15,
        "status": "inactive",
        "age_group": ["adulte"],
        "recipient_gender": ["unisex"],
        "occasion_score": {"anniversaire": 0.75},
        "tags": {
            "event": [{"slug": "anniversaire", "intensity": 0.7}],
            "theme": [{"slug": "handmade",     "intensity": 0.8}],
        },
    },
    {
        "name": "T_Bougie deco",
        "price": 18.0,
        "stock": 20,
        "status": "active",
        "age_group": ["adolescent", "adulte"],
        "recipient_gender": ["unisex"],
        "occasion_score": {"anniversaire": 0.65},
        "tags": {
            "event": [{"slug": "noel",       "intensity": 0.7}],
            "theme": [{"slug": "decorative", "intensity": 0.9}],
        },
    },
]


def _redact_mongo_url(database_url: str) -> str:
    if "@" not in database_url:
        return database_url
    scheme, rest = database_url.split("://", 1)
    _, host_and_path = rest.split("@", 1)
    return f"{scheme}://<redacted>@{host_and_path}"


class _InsertManyResult:
    def __init__(self, inserted_ids: list[Any]) -> None:
        self.inserted_ids = inserted_ids


class InMemoryCollection:
    def __init__(self) -> None:
        self._docs: list[dict[str, Any]] = []

    def drop(self) -> None:
        self._docs = []

    def insert_many(self, docs: list[dict[str, Any]]) -> _InsertManyResult:
        inserted_ids: list[Any] = []
        start_index = len(self._docs)
        for index, doc in enumerate(docs):
            stored = {**doc}
            stored.setdefault("_id", f"in-memory-{start_index + index}")
            inserted_ids.append(stored["_id"])
            self._docs.append(stored)
        return _InsertManyResult(inserted_ids)

    def insert_one(self, doc: dict[str, Any]):
        stored = {**doc}
        stored.setdefault("_id", f"in-memory-{len(self._docs)}")
        self._docs.append(stored)
        return type("InsertOneResult", (), {"inserted_id": stored["_id"]})()

    def delete_one(self, query: dict[str, Any]):
        for index, doc in enumerate(self._docs):
            if _matches_filter(doc, query):
                del self._docs[index]
                return type("DeleteResult", (), {"deleted_count": 1})()
        return type("DeleteResult", (), {"deleted_count": 0})()

    def find(
        self,
        query: dict[str, Any] | None = None,
        projection: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        query = query or {}
        docs = [
            _apply_projection({**doc}, projection)
            for doc in self._docs
            if _matches_filter(doc, query)
        ]
        return docs


class InMemoryDatabase:
    name = "giftyzi_test_memory"

    def __init__(self) -> None:
        self._collections: dict[str, InMemoryCollection] = {}

    def __getitem__(self, collection_name: str) -> InMemoryCollection:
        if collection_name not in self._collections:
            self._collections[collection_name] = InMemoryCollection()
        return self._collections[collection_name]


def _matches_filter(doc: dict[str, Any], query: dict[str, Any]) -> bool:
    for field, expected in query.items():
        actual = doc.get(field)
        if isinstance(expected, dict):
            if "$gt" in expected and not (actual is not None and actual > expected["$gt"]):
                return False
            if "$lte" in expected and not (actual is not None and actual <= expected["$lte"]):
                return False
            continue
        if actual != expected:
            return False
    return True


def _apply_projection(
    doc: dict[str, Any],
    projection: dict[str, int] | None,
) -> dict[str, Any]:
    if not projection:
        return doc
    if projection.get("_id") == 0:
        doc.pop("_id", None)
    return doc


@pytest.fixture
def api_client() -> TestClient:
    from app.main import app

    return TestClient(app)


@pytest.fixture
def nextjs_recommendation_payload() -> dict[str, Any]:
    return {
        "status": "active",
        "budget_max": 80.0,
        "hard_filters": {
            "recipient_gender": ["female"],
            "age_group": ["adulte"],
        },
        "soft_tags": {
            "event": [{"slug": "anniversaire", "intensity": 1.0}],
            "relationship": [{"slug": "partenaire", "intensity": 1.0}],
            "theme": [{"slug": "romantic", "intensity": 1.0}],
            "gift_benefit": [{"slug": "emotional", "intensity": 1.0}],
        },
        "facet_weights": {
            "event": 1.3,
            "relationship": 1.1,
            "theme": 0.9,
            "gift_benefit": 1.0,
        },
    }


@pytest.fixture
def mock_ranked_products() -> list[dict[str, Any]]:
    return [
        {
            "_id": "product-001",
            "product_id": "gift-romantic-001",
            "name": "Bougie bijou romantique",
            "price": 49.9,
            "stock": 7,
            "status": "active",
            "age_group": ["adulte"],
            "recipient_gender": ["female", "unisex"],
            "tags": {
                "event": [{"slug": "anniversaire", "intensity": 1.0}],
                "relationship": [{"slug": "partenaire", "intensity": 0.8}],
                "theme": [{"slug": "romantic", "intensity": 1.0}],
                "gift_benefit": [{"slug": "emotional", "intensity": 0.9}],
            },
            "_score": 3.42,
            "score": 0.95,
            "reason": "Stubbed ranked product.",
        }
    ]


@pytest.fixture(scope="session")
def test_db() -> InMemoryDatabase:
    db = InMemoryDatabase()
    logger.info("[conftest] Using in-memory Mongo database: '%s'", db.name)
    return db


@pytest.fixture(scope="session")
def inserted_products(test_db: InMemoryDatabase) -> Generator[list[dict], None, None]:
    collection = test_db[TEST_COLLECTION]
    collection.drop()
    result = collection.insert_many(TEST_PRODUCTS)

    assert len(result.inserted_ids) == len(TEST_PRODUCTS), (
        f"Expected {len(TEST_PRODUCTS)} inserts, got {len(result.inserted_ids)}."
    )
    logger.info(
        f"[conftest] Inserted {len(result.inserted_ids)} docs into '{TEST_COLLECTION}'."
    )

    docs = list(collection.find({}, {"_id": 0}))
    yield docs

    collection.drop()
    logger.info(f"[conftest] Cleanup: '{TEST_COLLECTION}' collection dropped.")


@pytest.fixture(autouse=True)
def use_in_memory_app_db(test_db: InMemoryDatabase, monkeypatch: pytest.MonkeyPatch):
    from app.db import client as db_client

    monkeypatch.setattr(db_client, "_db", test_db)
    yield
