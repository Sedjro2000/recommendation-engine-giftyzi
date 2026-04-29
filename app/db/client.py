import logging
import os

from pymongo import MongoClient
from pymongo.database import Database

logger = logging.getLogger(__name__)

_client: MongoClient | None = None
_db: Database | None = None


def _redact_mongo_url(database_url: str) -> str:
    if "@" not in database_url:
        return database_url
    scheme, rest = database_url.split("://", 1)
    _, host_and_path = rest.split("@", 1)
    return f"{scheme}://<redacted>@{host_and_path}"


def connect_to_mongo() -> None:
    global _client, _db

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not set.")

    logger.info(f"Connecting to MongoDB at {_redact_mongo_url(database_url)}...")
    try:
        _client = MongoClient(database_url, serverSelectionTimeoutMS=5000)
        _client.admin.command("ping")

        explicit_db = os.getenv("DB_NAME")
        if explicit_db:
            _db = _client[explicit_db]
        else:
            _db = _client.get_default_database()

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
