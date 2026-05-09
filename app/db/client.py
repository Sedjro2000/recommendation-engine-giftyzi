import logging
import os

from pymongo import MongoClient
from pymongo.database import Database

logger = logging.getLogger(__name__)

_client: MongoClient | None = None
_db: Database | None = None
DEFAULT_SERVER_SELECTION_TIMEOUT_MS = 30000


def _redact_mongo_url(database_url: str) -> str:
    if "@" not in database_url:
        return database_url
    scheme, rest = database_url.split("://", 1)
    _, host_and_path = rest.split("@", 1)
    return f"{scheme}://<redacted>@{host_and_path}"


def _mongo_server_selection_timeout_ms() -> int:
    raw_timeout = os.getenv("MONGO_SERVER_SELECTION_TIMEOUT_MS")
    if raw_timeout is None:
        return DEFAULT_SERVER_SELECTION_TIMEOUT_MS

    try:
        timeout = int(raw_timeout)
    except ValueError:
        logger.warning(
            "Invalid MONGO_SERVER_SELECTION_TIMEOUT_MS=%r. Falling back to %sms.",
            raw_timeout,
            DEFAULT_SERVER_SELECTION_TIMEOUT_MS,
        )
        return DEFAULT_SERVER_SELECTION_TIMEOUT_MS

    if timeout <= 0:
        logger.warning(
            "MONGO_SERVER_SELECTION_TIMEOUT_MS must be positive. Falling back to %sms.",
            DEFAULT_SERVER_SELECTION_TIMEOUT_MS,
        )
        return DEFAULT_SERVER_SELECTION_TIMEOUT_MS

    return timeout


def connect_to_mongo() -> None:
    global _client, _db

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL environment variable is not set.")

    logger.info(f"Connecting to MongoDB at {_redact_mongo_url(database_url)}...")
    try:
        timeout_ms = _mongo_server_selection_timeout_ms()
        _client = MongoClient(database_url, serverSelectionTimeoutMS=timeout_ms)
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
