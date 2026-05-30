"""Funnel schemas."""
from pydantic import BaseModel
from typing import List, Dict, Any


class FunnelStage(BaseModel):
    """Schema for a funnel stage."""
    stage: str
    label: str
    count: int
    pct: float
    drop_pct: float


class FunnelResponse(BaseModel):
    """Response schema for /funnel endpoint."""
    store_id: str
    date: str
    total_sessions: int
    stages: List[FunnelStage]
    avg_stages_reached: float
    biggest_drop_stage: str
