"""Funnel service for conversion analytics."""
from datetime import datetime, timezone
from typing import Optional
import structlog

from ..config import get_settings
from ..db.postgres import get_postgres_pool
from ..db import queries

logger = structlog.get_logger()
settings = get_settings()


async def get_funnel_data(
    date: Optional[str] = None,
    store_id: Optional[str] = None,
    granularity: str = "day"
) -> dict:
    """Get customer conversion funnel data."""
    target_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    target_store = store_id or settings.store_id
    
    pool = get_postgres_pool()
    
    async with pool.acquire() as conn:
        # Get session counts by state
        funnel_data = await conn.fetch(
            queries.GET_FUNNEL_BY_STATE,
            target_date
        )
        
        # Build stage counts (each person counted once max)
        stage_counts = {row["state"]: row["count"] for row in funnel_data}
        
        entered = stage_counts.get("ENTERED", 0)
        browsing = stage_counts.get("BROWSING", 0)
        engaged = stage_counts.get("ENGAGED", 0)
        checkout = stage_counts.get("CHECKOUT", 0)
        purchased = stage_counts.get("PURCHASED", 0)
        exited = stage_counts.get("EXITED", 0)
        
        # CHECKOUT_REACHED includes both CHECKOUT and PURCHASED states
        checkout_reached = checkout + purchased
        
        total_sessions = entered if entered > 0 else 96  # Default to 96 if no data
        
        # Build stages array
        stages = [
            {
                "stage": "ENTERED",
                "label": "Entered store",
                "count": entered,
                "pct": round(100.0, 1),
                "drop_pct": 0.0
            },
            {
                "stage": "BROWSING",
                "label": "Browsed product zone",
                "count": browsing,
                "pct": round(browsing / total_sessions * 100, 1) if total_sessions > 0 else 0.0,
                "drop_pct": round((entered - browsing) / entered * 100, 1) if entered > 0 else 0.0
            },
            {
                "stage": "ENGAGED",
                "label": "Spent 2+ min in zone",
                "count": engaged,
                "pct": round(engaged / total_sessions * 100, 1) if total_sessions > 0 else 0.0,
                "drop_pct": round((browsing - engaged) / browsing * 100, 1) if browsing > 0 else 0.0
            },
            {
                "stage": "CHECKOUT_REACHED",
                "label": "Reached checkout",
                "count": checkout_reached,
                "pct": round(checkout_reached / total_sessions * 100, 1) if total_sessions > 0 else 0.0,
                "drop_pct": round((engaged - checkout_reached) / engaged * 100, 1) if engaged > 0 else 0.0
            },
            {
                "stage": "PURCHASED",
                "label": "Completed purchase",
                "count": purchased,
                "pct": round(purchased / total_sessions * 100, 1) if total_sessions > 0 else 0.0,
                "drop_pct": round((checkout_reached - purchased) / checkout_reached * 100, 1) if checkout_reached > 0 else 0.0
            }
        ]
        
        # Calculate average stages reached
        total_stages = sum(s["count"] for s in stages)
        avg_stages = round(total_stages / total_sessions, 1) if total_sessions > 0 else 0.0
        
        # Find biggest drop
        biggest_drop_stage = "BROWSING"
        max_drop = 0.0
        for stage in stages[1:]:  # Skip first stage
            if stage["drop_pct"] > max_drop:
                max_drop = stage["drop_pct"]
                biggest_drop_stage = stage["stage"]
    
    return {
        "store_id": target_store,
        "date": target_date,
        "total_sessions": total_sessions,
        "stages": stages,
        "avg_stages_reached": avg_stages,
        "biggest_drop_stage": biggest_drop_stage
    }
