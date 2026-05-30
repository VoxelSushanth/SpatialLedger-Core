"""Event schemas."""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime


class EventSchema(BaseModel):
    """Schema for an event."""
    event_id: str
    event_type: str
    timestamp: str
    person_id: str
    person_type: str = "UNKNOWN"
    session_id: Optional[str] = None
    zone_id: Optional[str] = None
    camera_id: Optional[str] = None
    confidence: float = 0.9
    re_entry: bool = False
    group_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class EventsResponse(BaseModel):
    """Response for events endpoint."""
    total: int
    events: List[Dict[str, Any]]
    pagination: Dict[str, Any]
