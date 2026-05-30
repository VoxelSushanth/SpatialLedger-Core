"""Metrics router."""
from fastapi import APIRouter, Query
from typing import Optional

from ..services.metrics_svc import get_store_metrics
from ..schemas.metrics import MetricsResponse

router = APIRouter()


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    store_id: Optional[str] = Query(None, description="Store ID")
):
    """Get comprehensive store metrics including footfall, conversion, dwell time, and revenue."""
    return await get_store_metrics(date=date, store_id=store_id)
