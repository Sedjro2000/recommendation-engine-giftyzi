import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.db.client import close_mongo_connection, connect_to_mongo

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== GIFTYZI Recommendation Engine starting up ===")
    connect_to_mongo()
    yield
    close_mongo_connection()
    logger.info("=== GIFTYZI Recommendation Engine shut down ===")


app = FastAPI(
    title="GIFTYZI Recommendation Engine",
    version="0.1.0",
    description="MVP gift recommendation API backed by MongoDB.",
    lifespan=lifespan,
)

app.include_router(router, prefix="/api/v1", tags=["Recommendations"])
