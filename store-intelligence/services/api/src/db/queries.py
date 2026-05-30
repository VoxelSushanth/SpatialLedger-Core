"""Database queries for API services."""
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import asyncpg
import structlog

logger = structlog.get_logger()


class Queries:
    """Database query helpers."""

    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def get_sessions_by_state(self, date: str) -> Dict[str, int]:
        """Get session counts grouped by state for a date."""
        ist = timezone(timedelta(hours=5, minutes=30))
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=ist)
        except ValueError:
            target_date = datetime.now(ist)

        start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT state, COUNT(DISTINCT session_id) as count
                FROM sessions
                WHERE started_at >= $1 AND started_at < $2
                AND person_type = 'CUSTOMER'
                GROUP BY state
            """, start_of_day, end_of_day)

            return {row["state"]: row["count"] for row in rows}

    async def get_all_sessions(self, date: str) -> List[Dict[str, Any]]:
        """Get all sessions for a date."""
        ist = timezone(timedelta(hours=5, minutes=30))
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=ist)
        except ValueError:
            target_date = datetime.now(ist)

        start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM sessions
                WHERE started_at >= $1 AND started_at < $2
                ORDER BY started_at
            """, start_of_day, end_of_day)

            return [dict(row) for row in rows]

    async def get_transactions_summary(self, date: str) -> Dict[str, Any]:
        """Get transaction summary for metrics."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT 
                    SUM(gmv) as total_gmv,
                    SUM(nmv) as total_nmv,
                    COUNT(DISTINCT invoice_number) as total_transactions,
                    AVG(total_amount) as avg_basket_value
                FROM transactions
                WHERE order_date = $1
            """, date)

            return {
                "total_gmv": float(row["total_gmv"] or 0),
                "total_nmv": float(row["total_nmv"] or 0),
                "total_transactions": int(row["total_transactions"] or 0),
                "avg_basket_value": float(row["avg_basket_value"] or 0)
            }

    async def get_zone_metrics(self, date: str) -> List[Dict[str, Any]]:
        """Get zone visit metrics."""
        ist = timezone(timedelta(hours=5, minutes=30))
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=ist)
        except ValueError:
            target_date = datetime.now(ist)

        start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    zone_id,
                    COUNT(*) as visit_count,
                    COUNT(DISTINCT session_id) as unique_visitors,
                    AVG((metadata->>'dwell_seconds')::int) as avg_dwell_seconds
                FROM events
                WHERE event_type = 'ZONE_ENTER'
                AND timestamp >= $1 AND timestamp < $2
                GROUP BY zone_id
            """, start_of_day, end_of_day)

            return [dict(row) for row in rows]

    async def get_events(self, limit: int = 100, offset: int = 0,
                        event_type: Optional[str] = None,
                        person_type: Optional[str] = None,
                        date: Optional[str] = None,
                        camera_id: Optional[str] = None) -> Dict[str, Any]:
        """Query events with filters."""
        async with self.pool.acquire() as conn:
            conditions = ["1=1"]
            params = []
            param_count = 1

            if event_type:
                conditions.append(f"event_type = ${param_count}")
                params.append(event_type)
                param_count += 1

            if person_type:
                conditions.append(f"person_type = ${param_count}")
                params.append(person_type)
                param_count += 1

            if date:
                conditions.append(f"timestamp::date = ${param_count}")
                params.append(date)
                param_count += 1

            if camera_id:
                conditions.append(f"camera_id = ${param_count}")
                params.append(camera_id)
                param_count += 1

            where_clause = " AND ".join(conditions)

            # Get total count
            count_query = f"SELECT COUNT(*) FROM events WHERE {where_clause}"
            total = await conn.fetchval(count_query, *params)

            # Get events
            query = f"""
                SELECT * FROM events 
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ${param_count} OFFSET ${param_count + 1}
            """
            params.extend([limit, offset])
            rows = await conn.fetch(query, *params)

            events = []
            for row in rows:
                event_dict = dict(row)
                if event_dict.get("metadata"):
                    try:
                        event_dict["metadata"] = json.loads(event_dict["metadata"])
                    except Exception:
                        pass
                events.append(event_dict)

            return {
                "total": total,
                "events": events,
                "pagination": {
                    "limit": limit,
                    "offset": offset,
                    "next_offset": offset + len(events) if offset + len(events) < total else None
                }
            }

    async def get_anomalies(self, limit: int = 50, offset: int = 0,
                           severity: Optional[str] = None) -> Dict[str, Any]:
        """Get anomalies from database."""
        async with self.pool.acquire() as conn:
            if severity and severity.upper() != "ALL":
                rows = await conn.fetch("""
                    SELECT * FROM anomalies 
                    WHERE severity = $1 
                    ORDER BY detected_at DESC 
                    LIMIT $2 OFFSET $3
                """, severity.upper(), limit, offset)

                count_row = await conn.fetchval("""
                    SELECT COUNT(*) FROM anomalies WHERE severity = $1
                """, severity.upper())
            else:
                rows = await conn.fetch("""
                    SELECT * FROM anomalies 
                    ORDER BY detected_at DESC 
                    LIMIT $1 OFFSET $2
                """, limit, offset)

                count_row = await conn.fetchval("""
                    SELECT COUNT(*) FROM anomalies
                """)

            anomalies = []
            for row in rows:
                anomalies.append({
                    "id": str(row["anomaly_id"]),
                    "type": row["type"],
                    "severity": row["severity"],
                    "detected_at": row["detected_at"].isoformat() if row["detected_at"] else None,
                    "resolved_at": row["resolved_at"].isoformat() if row["resolved_at"] else None,
                    "description": row["description"],
                    "active": row["resolved_at"] is None
                })

            return {
                "total": count_row,
                "anomalies": anomalies
            }

    async def get_hourly_footfall(self, date: str) -> Dict[int, int]:
        """Get hourly footfall breakdown."""
        ist = timezone(timedelta(hours=5, minutes=30))
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=ist)
        except ValueError:
            target_date = datetime.now(ist)

        start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT EXTRACT(HOUR FROM timestamp) as hour, COUNT(*) as count
                FROM events
                WHERE event_type = 'ENTRY'
                AND person_type = 'CUSTOMER'
                AND timestamp >= $1 AND timestamp < $2
                GROUP BY hour
                ORDER BY hour
            """, start_of_day, end_of_day)

            return {int(row["hour"]): row["count"] for row in rows}
