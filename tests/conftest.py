"""
Test fixtures for GIFTYZI.

- Loads DATABASE_URL from app/.env (Atlas connection string).
- Uses dedicated collection `products_test` — never touches `products`.
- Session-scoped: insert once, yield to all tests, drop on teardown.
"""

import logging
import os
from pathlib import Path
from typing import Generator

import pytest
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv(dotenv_path=Path(__file__).parent.parent / "app" / ".env")

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


@pytest.fixture(scope="session")
def mongo_client() -> Generator[MongoClient, None, None]:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.fail("DATABASE_URL is not set. Cannot connect to MongoDB.")

    client = MongoClient(database_url, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
        logger.info(f"[conftest] MongoDB ping OK — {database_url[:40]}...")
    except Exception as exc:
        pytest.fail(f"MongoDB connection failed: {exc}")

    yield client
    client.close()
    logger.info("[conftest] MongoDB client closed.")


@pytest.fixture(scope="session")
def test_db(mongo_client: MongoClient) -> Database:
    explicit = os.getenv("DB_NAME")
    if explicit:
        db = mongo_client[explicit]
    else:
        try:
            db = mongo_client.get_default_database()
        except Exception:
            db = mongo_client["giftyzi"]
    logger.info(f"[conftest] Using database: '{db.name}'")
    return db


@pytest.fixture(scope="session")
def inserted_products(test_db: Database) -> Generator[list[dict], None, None]:
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
