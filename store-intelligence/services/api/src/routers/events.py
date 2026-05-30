"""Events router."""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List
from datetime import datetime, timezone
import uuid

from ..db.postgres import get_postgres_pool
from ..db import queries

router = APIRouter()


@router.get("/events")
async def get_events(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    person_type: Optional[str] = Query(None, description="Filter by person type"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    camera_id: Optional[str] = Query(None, description="Filter by camera ID")
):
    """Get raw events with pagination."""
    target_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    pool = get_postgres_pool()
    
    async with pool.acquire() as conn:
        # Get total count
        total = await conn.fetchval(
            queries.GET_EVENTS_COUNT,
            target_date,
            event_type,
            person_type,
            camera_id
        ) or 0
        
        # Get events
        event_rows = await conn.fetch(
            queries.GET_EVENTS,
            target_date,
            event_type,
            person_type,
            camera_id,
            limit,
            offset
        )
        
        events = [dict(row) for row in event_rows]
    
    next_offset = offset + limit if offset + limit < total else None
    
    return {
        "total": total,
        "events": events,
        "pagination": {
            "limit": limit,
            "offset": offset,
            "next_offset": next_offset
        }
    }


@router.post("/events", status_code=201)
async def create_event(event_data: dict):
    """Create a new event (for testing/manual injection)."""
    pool = get_postgres_pool()
    
    # Validate required fields
    required_fields = ["event_type", "timestamp", "person_id"]
    for field in required_fields:
        if field not in event_data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
    
    # Generate event_id if not provided
    if "event_id" not in event_data:
        event_data["event_id"] = str(uuid.uuid4())
    
    async with pool.acquire() as conn:
        try:
            await conn.execute(
                queries.INSERT_EVENT,
                event_data.get("event_id"),
                event_data["event_type"],
                event_data["timestamp"],
                event_data["person_id"],
                event_data.get("person_type", "UNKNOWN"),
                event_data.get("session_id"),
                event_data.get("zone_id"),
                event_data.get("camera_id"),
                event_data.get("confidence", 0.5),
                event_data.get("re_entry", False),
                event_data.get("group_id"),
                event_data.get("metadata", {})
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    return {
        "event_id": event_data["event_id"],
        "status": "created"
    }
