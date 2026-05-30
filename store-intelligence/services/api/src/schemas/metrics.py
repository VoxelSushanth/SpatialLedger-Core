"""Metrics schemas."""
from pydantic import BaseModel
from typing import Dict, Any, List, Optional


class MetricsResponse(BaseModel):
    """Response schema for /metrics endpoint."""
    store_id: str
    store_name: str
    date: str
    generated_at: str
    footfall: Dict[str, Any]
    conversion: Dict[str, Any]
    dwell_time: Dict[str, Any]
    revenue: Dict[str, Any]
    zone_popularity: List[Dict[str, Any]]
