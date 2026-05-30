"""Zone service for zone-level analytics."""
from datetime import datetime, timezone
from typing import Optional
import structlog

from ..config import get_settings
from ..db.postgres import get_postgres_pool
from ..db.redis_client import get_redis_client
from ..db import queries

logger = structlog.get_logger()
settings = get_settings()

ZONE_DISPLAY_NAMES = {
    "entrance": "Entrance",
    "makeup": "Makeup",
    "skincare": "Skincare",
    "hair": "Hair",
    "fragrance": "Fragrance",
    "personal_care": "Personal Care",
    "checkout": "Checkout",
    "unknown": "Unknown"
}


async def get_all_zones(date: Optional[str] = None) -> dict:
    """Get metrics for all zones."""
    target_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    pool = get_postgres_pool()
    redis = get_redis_client()
    
    zones = []
    for zone_id in ZONE_DISPLAY_NAMES.keys():
        zone_data = await get_zone_metrics(zone_id, target_date, pool, redis)
        zones.append(zone_data)
    
    return {"zones": zones}


async def get_zone_metrics(
    zone_id: str,
    date: Optional[str] = None,
    pool=None,
    redis=None
) -> dict:
    """Get metrics for a specific zone."""
    target_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    if pool is None:
        pool = get_postgres_pool()
    if redis is None:
        redis = get_redis_client()
    
    async with pool.acquire() as conn:
        # Get zone visit stats
        zone_stats = await conn.fetchrow(
            queries.GET_ZONE_STATS,
            zone_id,
            target_date
        )
        
        total_visits = int(zone_stats["total_visits"]) if zone_stats and zone_stats["total_visits"] else 0
        unique_visitors = int(zone_stats["unique_visitors"]) if zone_stats and zone_stats["unique_visitors"] else 0
        avg_dwell_seconds = int(zone_stats["avg_dwell_seconds"]) if zone_stats and zone_stats["avg_dwell_seconds"] else 0
        
        # Get hourly visits
        hourly_data = await conn.fetch(
            queries.GET_ZONE_HOURLY_VISITS,
            zone_id,
            target_date
        )
        hourly_visits = {str(row["hour"]): row["count"] for row in hourly_data}
        
        # Get peak occupancy
        peak_data = await conn.fetchrow(
            queries.GET_ZONE_PEAK_OCCUPANCY,
            zone_id,
            target_date
        )
        peak_occupancy = int(peak_data["peak_count"]) if peak_data and peak_data["peak_count"] else 0
        peak_time = peak_data["peak_time"].isoformat() if peak_data and peak_data["peak_time"] else None
    
    # Get current occupancy from Redis
    current_occupancy_key = f"metrics:zone:{zone_id}:count"
    current_occupancy = int(await redis.get(current_occupancy_key) or 0)
    
    return {
        "zone_id": zone_id,
        "display_name": ZONE_DISPLAY_NAMES.get(zone_id, zone_id),
        "metrics": {
            "total_visits": total_visits,
            "unique_visitors": unique_visitors,
            "avg_dwell_seconds": avg_dwell_seconds,
            "current_occupancy": current_occupancy,
            "peak_occupancy": peak_occupancy,
            "peak_occupancy_time": peak_time
        },
        "hourly_visits": hourly_visits
    }


async def get_zone_heatmap() -> dict:
    """Get current occupancy for all zones (for heatmap visualization)."""
    redis = get_redis_client()
    
    heatmap = {}
    for zone_id in ZONE_DISPLAY_NAMES.keys():
        key = f"metrics:zone:{zone_id}:count"
        occupancy = int(await redis.get(key) or 0)
        heatmap[zone_id] = {
            "display_name": ZONE_DISPLAY_NAMES.get(zone_id, zone_id),
            "current_occupancy": occupancy
        }
    
    return {"heatmap": heatmap}
