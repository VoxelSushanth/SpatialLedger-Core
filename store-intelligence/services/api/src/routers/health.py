"""Health check endpoints."""
from fastapi import APIRouter
from datetime import datetime, timezone
import asyncpg
import aioredis

from ..config import get_settings
from ..db.postgres import get_postgres_pool
from ..db.redis_client import get_redis_client

router = APIRouter()
settings = get_settings()


@router.get("/health")
async def health_check():
    """Basic health check - always returns 200 if service is running."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "store-intelligence-api"
    }


@router.get("/ready")
async def readiness_check():
    """Check if all dependencies are ready."""
    result = {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {}
    }
    
    # Check PostgreSQL
    try:
        pool = get_postgres_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        result["checks"]["postgres"] = "ok"
    except Exception as e:
        result["checks"]["postgres"] = f"error: {str(e)}"
        result["status"] = "degraded"
    
    # Check Redis
    try:
        redis = get_redis_client()
        await redis.ping()
        result["checks"]["redis"] = "ok"
    except Exception as e:
        result["checks"]["redis"] = f"error: {str(e)}"
        result["status"] = "degraded"
    
    status_code = 200 if result["status"] == "ok" else 503
    return result, status_code


@router.get("/metrics/prometheus")
async def prometheus_metrics():
    """Prometheus metrics endpoint."""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from fastapi.responses import Response
    
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST
    )
