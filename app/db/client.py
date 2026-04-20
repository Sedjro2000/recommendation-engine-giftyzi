import logging
import os

from pymongo import MongoClient
from pymongo.database import Database

logger = logging.getLogger(__name__)

_client: MongoClient | None = None
_db: Database | None = None


def connect_to_mongo() -> None:
    global _client, _db

    database_url = os.getenv("DATABASE_URL", "mongodb://localhost:27017")

    logger.info(f"Connecting to MongoDB at {database_url}...")
    try:
        _client = MongoClient(database_url, serverSelectionTimeoutMS=5000)
        _client.admin.command("ping")

        explicit_db = os.getenv("DB_NAME")
        if explicit_db:
            _db = _client[explicit_db]
        else:
            try:
                _db = _client.get_default_database()
            except Exception:
                _db = _client["giftyzi"]

        logger.info(f"Using database: '{_db.name}'")
        logger.info("MongoDB connection established and ping successful.")
    except Exception as exc:
        logger.error(f"Failed to connect to MongoDB: {exc}")
        raise


def close_mongo_connection() -> None:
    global _client
    if _client is not None:
        _client.close()
        logger.info("MongoDB connection closed.")


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("Database not initialized. Call connect_to_mongo() on startup.")
    return _db
