"""Funnel router."""
from fastapi import APIRouter, Query
from typing import Optional

from ..services.funnel_svc import get_funnel_data
from ..schemas.funnel import FunnelResponse

router = APIRouter()


@router.get("/funnel", response_model=FunnelResponse)
async def get_funnel(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format"),
    store_id: Optional[str] = Query(None, description="Store ID"),
    granularity: str = Query("day", description="Granularity: hour or day")
):
    """Get customer conversion funnel data."""
    return await get_funnel_data(date=date, store_id=store_id, granularity=granularity)
