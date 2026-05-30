"""Anomalies router."""
from fastapi import APIRouter, Query
from typing import Optional

from ..services.anomaly_svc import get_anomalies

router = APIRouter()


@router.get("/anomalies")
async def get_anomalies_endpoint(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    severity: Optional[str] = Query("all", description="Filter by severity (HIGH|MEDIUM|LOW|all)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
):
    """Get detected anomalies with filtering and pagination."""
    return await get_anomalies(
        date=date,
        severity=severity,
        limit=limit,
        offset=offset
    )
