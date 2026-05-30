"""Zones router."""
from fastapi import APIRouter, Query
from typing import Optional

from ..services.zone_svc import get_all_zones, get_zone_metrics, get_zone_heatmap

router = APIRouter()


@router.get("/zones")
async def get_zones(
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format")
):
    """Get metrics for all zones."""
    return await get_all_zones(date=date)


@router.get("/zones/{zone_id}")
async def get_zone(
    zone_id: str,
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format")
):
    """Get metrics for a specific zone."""
    return await get_zone_metrics(zone_id=zone_id, date=date)


@router.get("/zones/heatmap")
async def get_heatmap():
    """Get current occupancy heatmap for all zones."""
    return await get_zone_heatmap()
