"""Main FastAPI application."""
from fastapi import FastAPI
from contextlib import asynccontextmanager
import structlog

from .config import get_settings
from .db.postgres import init_postgres, close_postgres
from .db.redis_client import init_redis, close_redis
from .routers import metrics, funnel, events, anomalies, zones, health, ws

logger = structlog.get_logger()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting API service", store_id=settings.store_id)
    await init_postgres()
    await init_redis()
    logger.info("Database connections initialized")
    
    yield
    
    # Shutdown
    logger.info("Shutting down API service")
    await close_postgres()
    await close_redis()


app = FastAPI(
    title="Store Intelligence API",
    description="Purplle Store Intelligence System - Brigade Bangalore",
    version="1.0.0",
    lifespan=lifespan
)

# Include routers
app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
app.include_router(funnel.router, prefix="/api/v1", tags=["funnel"])
app.include_router(events.router, prefix="/api/v1", tags=["events"])
app.include_router(anomalies.router, prefix="/api/v1", tags=["anomalies"])
app.include_router(zones.router, prefix="/api/v1", tags=["zones"])
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(ws.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Store Intelligence API",
        "store_id": settings.store_id,
        "store_name": settings.store_name,
        "docs": "/docs"
    }
