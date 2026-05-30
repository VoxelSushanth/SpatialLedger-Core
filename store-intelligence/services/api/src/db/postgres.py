"""Database connection management."""
from typing import Optional
import asyncpg
import aioredis
import structlog

logger = structlog.get_logger()


class Database:
    """PostgreSQL connection manager."""

    def __init__(self, url: str):
        self.url = url
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Create connection pool."""
        self.pool = await asyncpg.create_pool(
            self.url,
            min_size=2,
            max_size=10
        )
        logger.info("Database connected")

    async def disconnect(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("Database disconnected")

    async def is_healthy(self) -> bool:
        """Check database health."""
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False


class RedisClient:
    """Redis connection manager."""

    def __init__(self, url: str):
        self.url = url
        self.redis: Optional[aioredis.Redis] = None

    async def connect(self):
        """Connect to Redis."""
        self.redis = await aioredis.from_url(
            self.url,
            encoding="utf-8",
            decode_responses=True
        )
        logger.info("Redis connected")

    async def disconnect(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
            logger.info("Redis disconnected")

    async def is_healthy(self) -> bool:
        """Check Redis health."""
        try:
            await self.redis.ping()
            return True
        except Exception:
            return False
