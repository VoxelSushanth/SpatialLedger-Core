"""Session store using Redis and PostgreSQL."""
import json
from typing import Dict, Optional, Any
from datetime import datetime, timedelta, timezone
import aioredis
import asyncpg
import structlog

from .state_machine import SessionStateMachine, PersonState

logger = structlog.get_logger()


class SessionStore:
    """Manages session storage in Redis (live) and PostgreSQL (persisted)."""

    def __init__(self, redis_url: str, postgres_url: str):
        self.redis_url = redis_url
        self.postgres_url = postgres_url
        self.redis: Optional[aioredis.Redis] = None
        self.postgres: Optional[asyncpg.Pool] = None
        self.session_ttl = 24 * 3600  # 24 hours
        self.re_entry_window = 3600  # 60 minutes
        
        # Track person exit times for re-entry detection
        self.person_exit_times: Dict[str, datetime] = {}

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
            max_size=10
        )
        
        logger.info("SessionStore connected to Redis and PostgreSQL")

    async def close(self):
        """Close connections."""
        if self.redis:
            await self.redis.close()
        if self.postgres:
            await self.postgres.close()
        logger.info("SessionStore connections closed")

    def _session_key(self, session_id: str) -> str:
        """Get Redis key for a session."""
        return f"session:{session_id}"

    def _person_key(self, person_id: str) -> str:
        """Get Redis key for person's last session."""
        return f"person:{person_id}:last_session"

    async def get_active_session(self, person_id: str) -> Optional[SessionStateMachine]:
        """
        Get active session for a person.
        
        Checks Redis first. If found, deserializes and returns.
        Also checks for re-entry within 60 minutes.
        """
        # Check for recent exit (re-entry window)
        person_key = self._person_key(person_id)
        last_session_data = await self.redis.get(person_key)
        
        if last_session_data:
            data = json.loads(last_session_data)
            ended_at_str = data.get("ended_at")
            
            if ended_at_str:
                try:
                    ended_at = datetime.fromisoformat(ended_at_str.replace("+05:30", "+05:30"))
                    now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
                    
                    if (now - ended_at).total_seconds() < self.re_entry_window:
                        # Re-entry within window - restore session
                        session = self._deserialize_session(data)
                        session.re_entry = True
                        logger.debug("Re-entry session restored", person_id=person_id)
                        return session
                except Exception as e:
                    logger.warning("Error parsing ended_at", error=str(e))
        
        return None

    async def create_session(self, person_id: str, timestamp: datetime, 
                            session_id: Optional[str] = None,
                            group_id: Optional[str] = None) -> SessionStateMachine:
        """Create a new session for a person."""
        if session_id is None:
            session_id = f"sess_{person_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        session = SessionStateMachine(
            session_id=session_id,
            person_id=person_id,
            started_at=timestamp
        )
        session.group_id = group_id
        
        await self._save_to_redis(session)
        logger.debug("New session created", session_id=session_id, person_id=person_id)
        
        return session

    async def update_session(self, machine: SessionStateMachine):
        """Update an existing session in Redis."""
        await self._save_to_redis(machine)

    async def close_session(self, machine: SessionStateMachine):
        """
        Close a session - move from Redis to PostgreSQL.
        """
        # Save to PostgreSQL
        await self._save_to_postgres(machine)
        
        # Remove from Redis
        session_key = self._session_key(machine.session_id)
        await self.redis.delete(session_key)
        
        # Store person's last session info for re-entry detection
        person_key = self._person_key(machine.person_id)
        await self.redis.setex(
            person_key,
            self.re_entry_window * 2,  # Keep for 2x re-entry window
            json.dumps(machine.to_dict())
        )
        
        # Track exit time
        if machine.ended_at:
            self.person_exit_times[machine.person_id] = machine.ended_at
        
        logger.info("Session closed and persisted", session_id=machine.session_id)

    async def _save_to_redis(self, machine: SessionStateMachine):
        """Save session to Redis with TTL."""
        session_key = self._session_key(machine.session_id)
        data = json.dumps(machine.to_dict())
        await self.redis.setex(session_key, self.session_ttl, data)

    async def _save_to_postgres(self, machine: SessionStateMachine):
        """Persist session to PostgreSQL."""
        async with self.postgres.acquire() as conn:
            await conn.execute("""
                INSERT INTO sessions (
                    session_id, person_id, person_type, state,
                    started_at, ended_at, dwell_seconds,
                    zones_visited, re_entry, group_id
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (session_id) DO UPDATE SET
                    state = EXCLUDED.state,
                    ended_at = EXCLUDED.ended_at,
                    dwell_seconds = EXCLUDED.dwell_seconds,
                    zones_visited = EXCLUDED.zones_visited
            """,
                machine.session_id,
                machine.person_id,
                machine.person_type,
                machine.state.value,
                machine.started_at,
                machine.ended_at,
                machine.dwell_seconds,
                machine.zones_visited,
                machine.re_entry,
                machine.group_id
            )

    def _deserialize_session(self, data: Dict[str, Any]) -> SessionStateMachine:
        """Deserialize session from dict."""
        session = SessionStateMachine(
            session_id=data["session_id"],
            person_id=data["person_id"],
            started_at=datetime.fromisoformat(data["started_at"].replace("+05:30", "+05:30"))
        )
        session.state = PersonState(data["state"])
        session.ended_at = datetime.fromisoformat(data["ended_at"].replace("+05:30", "+05:30")) if data.get("ended_at") else None
        session.dwell_seconds = data.get("dwell_seconds", 0)
        session.zones_visited = data.get("zones_visited", [])
        session.re_entry = data.get("re_entry", False)
        session.group_id = data.get("group_id")
        session.person_type = data.get("person_type", "CUSTOMER")
        
        return session

    async def get_all_active_sessions(self) -> list:
        """Get all active (non-terminal) sessions."""
        sessions = []
        cursor = 0
        
        while True:
            keys = await self.redis.keys("session:*")
            if not keys:
                break
                
            for key in keys:
                data = await self.redis.get(key)
                if data:
                    session_data = json.loads(data)
                    state = session_data.get("state", "")
                    if state not in ("EXITED", "PURCHASED"):
                        sessions.append(self._deserialize_session(session_data))
            break
        
        return sessions

    async def get_sessions_by_state(self, state: str) -> list:
        """Get sessions filtered by state."""
        # Query PostgreSQL for historical sessions
        async with self.postgres.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM sessions WHERE state = $1",
                state
            )
            return [dict(row) for row in rows]
