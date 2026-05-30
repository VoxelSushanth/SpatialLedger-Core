"""Database writer for persisting events and sessions."""
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import asyncpg
import structlog

logger = structlog.get_logger()


class DBWriter:
    """Writes events and sessions to PostgreSQL."""

    def __init__(self, postgres_url: str):
        self.postgres_url = postgres_url
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Create connection pool."""
        self.pool = await asyncpg.create_pool(
            self.postgres_url,
            min_size=2,
            max_size=10
        )
        logger.info("DBWriter connected to PostgreSQL")

    async def close(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
            logger.info("DBWriter disconnected")

    async def write_event(self, event: Dict[str, Any]):
        """Write a single event to the database."""
        async with self.pool.acquire() as conn:
            metadata = event.get("metadata", {})
            if isinstance(metadata, dict):
                metadata = json.dumps(metadata)
            
            await conn.execute("""
                INSERT INTO events (
                    event_id, event_type, timestamp, person_id, person_type,
                    session_id, zone_id, camera_id, confidence, re_entry,
                    group_id, metadata
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (event_id) DO NOTHING
            """,
                event.get("event_id"),
                event.get("event_type"),
                self._parse_timestamp(event.get("timestamp")),
                event.get("person_id"),
                event.get("person_type", "UNKNOWN"),
                event.get("session_id"),
                event.get("zone_id"),
                event.get("camera_id"),
                event.get("confidence"),
                event.get("re_entry", False),
                event.get("group_id"),
                metadata
            )

    async def write_events_batch(self, events: List[Dict[str, Any]]):
        """Write multiple events in a batch."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for event in events:
                    metadata = event.get("metadata", {})
                    if isinstance(metadata, dict):
                        metadata = json.dumps(metadata)
                    
                    await conn.execute("""
                        INSERT INTO events (
                            event_id, event_type, timestamp, person_id, person_type,
                            session_id, zone_id, camera_id, confidence, re_entry,
                            group_id, metadata
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                        ON CONFLICT (event_id) DO NOTHING
                    """,
                        event.get("event_id"),
                        event.get("event_type"),
                        self._parse_timestamp(event.get("timestamp")),
                        event.get("person_id"),
                        event.get("person_type", "UNKNOWN"),
                        event.get("session_id"),
                        event.get("zone_id"),
                        event.get("camera_id"),
                        event.get("confidence"),
                        event.get("re_entry", False),
                        event.get("group_id"),
                        metadata
                    )

    async def get_events(self, limit: int = 100, offset: int = 0,
                        event_type: Optional[str] = None,
                        person_type: Optional[str] = None,
                        date: Optional[str] = None,
                        camera_id: Optional[str] = None) -> Dict[str, Any]:
        """Query events with filters."""
        async with self.pool.acquire() as conn:
            # Build query
            conditions = ["1=1"]
            params = [limit, offset]
            param_count = 2
            
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
            total = await conn.fetchval(count_query, *params[2:])
            
            # Get events
            query = f"""
                SELECT * FROM events 
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT $1 OFFSET $2
            """
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

    async def get_sessions_for_funnel(self, date: str) -> List[Dict[str, Any]]:
        """Get sessions grouped by state for funnel calculation."""
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
            
            return [dict(row) for row in rows]

    async def get_all_sessions(self, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all sessions for a date."""
        if date:
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
        else:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("SELECT * FROM sessions ORDER BY started_at DESC LIMIT 1000")
                return [dict(row) for row in rows]

    async def get_transactions_summary(self, date: str) -> Dict[str, Any]:
        """Get transaction summary for metrics."""
        async with self.pool.acquire() as conn:
            # Total GMV and NMV
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

    def _parse_timestamp(self, ts_str: Optional[str]) -> Optional[datetime]:
        """Parse ISO8601 timestamp string."""
        if not ts_str:
            return None
        try:
            return datetime.fromisoformat(ts_str.replace("+05:30", "+05:30"))
        except Exception:
            return datetime.now()
