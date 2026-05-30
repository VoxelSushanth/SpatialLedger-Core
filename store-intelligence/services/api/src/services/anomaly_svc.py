"""Anomaly service for detecting store anomalies."""
from datetime import datetime, timezone
from typing import Optional, List
import structlog

from ..config import get_settings
from ..db.postgres import get_postgres_pool
from ..db import queries

logger = structlog.get_logger()
settings = get_settings()


async def get_anomalies(
    date: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> dict:
    """Get detected anomalies."""
    target_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    
    pool = get_postgres_pool()
    
    async with pool.acquire() as conn:
        # Get total count
        total = await conn.fetchval(
            queries.GET_ANOMALIES_COUNT,
            target_date,
            severity if severity and severity != "all" else None
        ) or 0
        
        # Get anomalies
        anomaly_rows = await conn.fetch(
            queries.GET_ANOMALIES,
            target_date,
            severity if severity and severity != "all" else None,
            limit,
            offset
        )
        
        anomalies = [
            {
                "id": str(row["anomaly_id"]),
                "type": row["type"],
                "severity": row["severity"],
                "detected_at": row["detected_at"].isoformat() if row["detected_at"] else None,
                "resolved_at": row["resolved_at"].isoformat() if row["resolved_at"] else None,
                "description": row["description"],
                "active": row["resolved_at"] is None
            }
            for row in anomaly_rows
        ]
    
    return {
        "total": total,
        "anomalies": anomalies
    }
