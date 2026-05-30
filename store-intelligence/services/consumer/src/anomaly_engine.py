"""Anomaly detection engine."""
import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
import aioredis
import asyncpg
import structlog
import uuid

logger = structlog.get_logger()


class AnomalyType:
    """Anomaly type constants."""
    CROWD_SURGE = "CROWD_SURGE"
    DWELL_OUTLIER = "DWELL_OUTLIER"
    LOW_CONVERSION_WINDOW = "LOW_CONVERSION_WINDOW"
    STAFF_ABSENT = "STAFF_ABSENT"


class Severity:
    """Severity levels."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class AnomalyEngine:
    """Detects and stores anomalies in store operations."""

    def __init__(self, redis_url: str, postgres_url: str):
        self.redis_url = redis_url
        self.postgres_url = postgres_url
        self.redis: Optional[aioredis.Redis] = None
        self.postgres: Optional[asyncpg.Pool] = None
        
        # Thresholds
        self.crowd_surge_threshold = 15  # >15 customers simultaneously
        self.dwell_outlier_threshold = 5400  # 90 minutes
        self.low_conversion_entries = 8  # >8 entries with 0 purchases
        self.staff_absent_minutes = 20
        
        # State tracking
        self.last_crowd_check = 0
        self.detected_anomalies: Dict[str, bool] = {}  # anomaly_key -> active

    async def connect(self):
        """Connect to Redis and PostgreSQL."""
        self.redis = await aioredis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
        
        self.postgres = await asyncpg.create_pool(
            self.postgres_url,
            min_size=2,
            max_size=5
        )
        
        logger.info("AnomalyEngine connected")

    async def close(self):
        """Close connections."""
        if self.redis:
            await self.redis.close()
        if self.postgres:
            await self.postgres.close()

    async def check_all_anomalies(self):
        """Run all anomaly detection checks."""
        await self._check_crowd_surge()
        await self._check_dwell_outliers()
        await self._check_low_conversion_window()
        await self._check_staff_absent()

    async def _check_crowd_surge(self):
        """Check for crowd surge (>15 customers simultaneously)."""
        try:
            # Get current zone counts
            zone_counts = await self.redis.hgetall("metrics:zone_counts")
            total_customers = sum(int(v) for v in zone_counts.values()) if zone_counts else 0
            
            # Also count from active sessions
            keys = await self.redis.keys("session:*")
            active_count = 0
            for key in keys:
                data = await self.redis.get(key)
                if data:
                    session_data = json.loads(data)
                    state = session_data.get("state", "")
                    if state not in ("EXITED", "PURCHASED"):
                        person_type = session_data.get("person_type", "CUSTOMER")
                        if person_type == "CUSTOMER":
                            active_count += 1
            
            total = max(total_customers, active_count)
            
            if total > self.crowd_surge_threshold:
                anomaly_key = f"{AnomalyType.CROWD_SURGE}:{datetime.now().strftime('%Y-%m-%d %H')}"
                
                if not self.detected_anomalies.get(anomaly_key):
                    await self._create_anomaly(
                        anomaly_type=AnomalyType.CROWD_SURGE,
                        severity=Severity.HIGH,
                        description=f"{total} customers detected simultaneously at {datetime.now().strftime('%H:%M')} IST",
                        metadata={"customer_count": total}
                    )
                    self.detected_anomalies[anomaly_key] = True
                    
        except Exception as e:
            logger.warning("Error checking crowd surge", error=str(e))

    async def _check_dwell_outliers(self):
        """Check for sessions with dwell time > 90 minutes."""
        try:
            keys = await self.redis.keys("session:*")
            for key in keys:
                data = await self.redis.get(key)
                if data:
                    session_data = json.loads(data)
                    dwell_seconds = session_data.get("dwell_seconds", 0)
                    
                    if dwell_seconds > self.dwell_outlier_threshold:
                        session_id = session_data.get("session_id")
                        anomaly_key = f"{AnomalyType.DWELL_OUTLIER}:{session_id}"
                        
                        if not self.detected_anomalies.get(anomaly_key):
                            await self._create_anomaly(
                                anomaly_type=AnomalyType.DWELL_OUTLIER,
                                severity=Severity.MEDIUM,
                                description=f"Session {session_id} has dwell time of {dwell_seconds // 60} minutes (threshold: {self.dwell_outlier_threshold // 60} min)",
                                metadata={"session_id": session_id, "dwell_seconds": dwell_seconds}
                            )
                            self.detected_anomalies[anomaly_key] = True
                            
        except Exception as e:
            logger.warning("Error checking dwell outliers", error=str(e))

    async def _check_low_conversion_window(self):
        """Check for 30-min windows with >8 entries and 0 purchases."""
        try:
            # Get recent sessions from PostgreSQL
            ist = timezone(timedelta(hours=5, minutes=30))
            now = datetime.now(ist)
            thirty_min_ago = now - timedelta(minutes=30)
            
            async with self.postgres.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT state, COUNT(*) as cnt 
                    FROM sessions 
                    WHERE started_at >= $1 
                    GROUP BY state
                """, thirty_min_ago)
                
                state_counts = {row["state"]: row["cnt"] for row in rows}
                
                entered_count = state_counts.get("ENTERED", 0) + state_counts.get("BROWSING", 0) + \
                               state_counts.get("ENGAGED", 0) + state_counts.get("CHECKOUT", 0)
                purchased_count = state_counts.get("PURCHASED", 0)
                
                if entered_count > self.low_conversion_entries and purchased_count == 0:
                    anomaly_key = f"{AnomalyType.LOW_CONVERSION_WINDOW}:{now.strftime('%Y-%m-%d %H')}"
                    
                    if not self.detected_anomalies.get(anomaly_key):
                        await self._create_anomaly(
                            anomaly_type=AnomalyType.LOW_CONVERSION_WINDOW,
                            severity=Severity.MEDIUM,
                            description=f"Last 30 minutes: {entered_count} entries, 0 purchases",
                            metadata={"entries": entered_count, "purchases": purchased_count}
                        )
                        self.detected_anomalies[anomaly_key] = True
                        
        except Exception as e:
            logger.warning("Error checking low conversion window", error=str(e))

    async def _check_staff_absent(self):
        """Check for no staff detected for >20 minutes during operating hours."""
        try:
            # Check for staff sessions
            keys = await self.redis.keys("session:*")
            staff_active = False
            
            for key in keys:
                data = await self.redis.get(key)
                if data:
                    session_data = json.loads(data)
                    if session_data.get("person_type") == "STAFF":
                        state = session_data.get("state", "")
                        if state not in ("EXITED", "PURCHASED"):
                            staff_active = True
                            break
            
            # Operating hours: 12:15 to 21:40
            ist = timezone(timedelta(hours=5, minutes=30))
            now = datetime.now(ist)
            open_time = now.replace(hour=12, minute=15, second=0, microsecond=0)
            close_time = now.replace(hour=21, minute=40, second=0, microsecond=0)
            
            if open_time <= now <= close_time and not staff_active:
                anomaly_key = f"{AnomalyType.STAFF_ABSENT}:{now.strftime('%Y-%m-%d %H')}"
                
                if not self.detected_anomalies.get(anomaly_key):
                    await self._create_anomaly(
                        anomaly_type=AnomalyType.STAFF_ABSENT,
                        severity=Severity.LOW,
                        description=f"No staff detected for {self.staff_absent_minutes}+ minutes during operating hours",
                        metadata={"check_time": now.isoformat()}
                    )
                    self.detected_anomalies[anomaly_key] = True
                    
        except Exception as e:
            logger.warning("Error checking staff absent", error=str(e))

    async def _create_anomaly(self, anomaly_type: str, severity: str, 
                             description: str, metadata: Optional[Dict] = None):
        """Create and store an anomaly."""
        anomaly_id = str(uuid.uuid4())
        ist = timezone(timedelta(hours=5, minutes=30))
        detected_at = datetime.now(ist)
        
        # Insert into PostgreSQL
        async with self.postgres.acquire() as conn:
            await conn.execute("""
                INSERT INTO anomalies (anomaly_id, type, severity, detected_at, description, metadata)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, anomaly_id, anomaly_type, severity, detected_at, description, 
                   json.dumps(metadata) if metadata else None)
        
        # Publish to Redis pub/sub for WebSocket push
        message = {
            "type": "anomaly",
            "data": {
                "id": anomaly_id,
                "type": anomaly_type,
                "severity": severity,
                "detected_at": detected_at.isoformat(),
                "resolved_at": None,
                "description": description,
                "active": True
            }
        }
        
        await self.redis.publish("store:anomalies", json.dumps(message))
        
        logger.warning(
            "Anomaly detected",
            type=anomaly_type,
            severity=severity,
            description=description
        )

    async def get_recent_anomalies(self, limit: int = 50, offset: int = 0,
                                   severity: Optional[str] = None) -> Dict[str, Any]:
        """Get recent anomalies from database."""
        async with self.postgres.acquire() as conn:
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
