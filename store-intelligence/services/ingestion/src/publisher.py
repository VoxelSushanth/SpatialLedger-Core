"""Redis Stream publisher for events."""
import json
import asyncio
from typing import Dict, Any, Optional
import aioredis
import structlog

logger = structlog.get_logger()


class EventPublisher:
    """Publishes events to Redis Streams and maintains counters."""

    def __init__(self, redis_url: str = "redis://redis:6379"):
        self.redis_url = redis_url
        self.redis: Optional[aioredis.Redis] = None
        self.stream_name = "store:events"
        logger.info("EventPublisher initialized", stream=stream_name)

    async def connect(self):
        """Connect to Redis."""
        self.redis = await aioredis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
        logger.info("EventPublisher connected to Redis")

    async def close(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
            logger.info("EventPublisher disconnected from Redis")

    async def publish(self, event: Dict[str, Any]) -> str:
        """
        Publish an event to Redis Stream.
        
        Args:
            event: Event dict conforming to schema
            
        Returns:
            Message ID in stream
        """
        if not self.redis:
            await self.connect()

        # Convert event to string values for Redis
        event_data = {k: str(v) if not isinstance(v, (str, int, float, bool)) else v 
                      for k, v in event.items()}
        
        # Handle nested metadata
        if "metadata" in event and isinstance(event["metadata"], dict):
            event_data["metadata"] = json.dumps(event["metadata"])

        message_id = await self.redis.xadd(self.stream_name, event_data)
        
        # Update counters based on event type
        await self._update_counters(event)
        
        return message_id

    async def _update_counters(self, event: Dict[str, Any]):
        """Update Redis counters atomically based on event."""
        event_type = event.get("event_type")
        person_type = event.get("person_type", "UNKNOWN")
        zone_id = event.get("zone_id")

        # Only count CUSTOMER events for footfall
        if person_type != "CUSTOMER":
            return

        if event_type == "ENTRY":
            await self.redis.incr("metrics:footfall:total")
            if not event.get("re_entry", False):
                await self.redis.incr("metrics:footfall:unique")

        elif event_type == "EXIT":
            await self.redis.incr("metrics:exits:total")

        elif event_type == "ZONE_ENTER" and zone_id:
            await self.redis.hincrby("metrics:zone_counts", zone_id, 1)

        elif event_type == "ZONE_EXIT" and zone_id:
            await self.redis.hincrby("metrics:zone_counts", zone_id, -1)

    async def get_counter(self, key: str) -> int:
        """Get a counter value."""
        if not self.redis:
            await self.connect()
        value = await self.redis.get(key)
        return int(value) if value else 0

    async def get_zone_counts(self) -> Dict[str, int]:
        """Get current occupancy for all zones."""
        if not self.redis:
            await self.connect()
        counts = await self.redis.hgetall("metrics:zone_counts")
        return {k: int(v) for k, v in counts.items()}

    async def trim_stream(self, max_age_hours: int = 24):
        """Trim stream to last N hours of events."""
        if not self.redis:
            await self.connect()
        
        # Calculate timestamp threshold
        from datetime import datetime, timedelta
        threshold = datetime.now() - timedelta(hours=max_age_hours)
        threshold_str = threshold.strftime("%Y-%m-%d %H:%M:%S")
        
        # Trim by timestamp
        await self.redis.xtrim(self.stream_name, minid=threshold_str)
        logger.info("Stream trimmed", max_age_hours=max_age_hours)

    async def publish_to_pubsub(self, channel: str, message: Dict[str, Any]):
        """Publish message to Redis pub/sub channel."""
        if not self.redis:
            await self.connect()
        await self.redis.publish(channel, json.dumps(message))
