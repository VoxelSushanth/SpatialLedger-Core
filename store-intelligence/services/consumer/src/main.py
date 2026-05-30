"""Main consumer service - processes events from Redis Streams."""
import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
import aioredis
import structlog

from .config import get_config
from .state_machine import SessionStateMachine, PersonState
from .session_store import SessionStore
from .anomaly_engine import AnomalyEngine
from .db_writer import DBWriter

logger = structlog.get_logger()


class ConsumerService:
    """Consumes events from Redis Streams and manages sessions."""

    def __init__(self):
        self.config = get_config()
        self.session_store: Optional[SessionStore] = None
        self.anomaly_engine: Optional[AnomalyEngine] = None
        self.db_writer: Optional[DBWriter] = None
        self.redis: Optional[aioredis.Redis] = None
        
        # Track processed events to avoid duplicates
        self.processed_events: set = set()
        self.max_processed_cache = 10000

    async def start(self):
        """Start the consumer service."""
        logger.info("Starting ConsumerService", store_id=self.config.store_id)
        
        # Initialize components
        self.session_store = SessionStore(
            redis_url=self.config.redis_url,
            postgres_url=self.config.postgres_url
        )
        await self.session_store.connect()
        
        self.anomaly_engine = AnomalyEngine(
            redis_url=self.config.redis_url,
            postgres_url=self.config.postgres_url
        )
        await self.anomaly_engine.connect()
        
        self.db_writer = DBWriter(self.config.postgres_url)
        await self.db_writer.connect()
        
        self.redis = await aioredis.from_url(
            self.config.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
        
        logger.info("ConsumerService initialized, starting event processing")
        
        # Start anomaly detection loop
        asyncio.create_task(self._anomaly_detection_loop())
        
        # Process events from stream
        await self._process_events()

    async def _process_events(self):
        """Continuously process events from Redis Stream."""
        stream_name = "store:events"
        last_id = "0"
        
        while True:
            try:
                # Read from stream
                messages = await self.redis.xread(
                    {stream_name: last_id},
                    count=100,
                    block=5000  # Block for 5 seconds
                )
                
                if not messages:
                    continue
                
                for stream, stream_messages in messages:
                    for message_id, event_data in stream_messages:
                        last_id = message_id
                        
                        # Skip if already processed
                        if message_id in self.processed_events:
                            continue
                        
                        await self._handle_event(event_data)
                        
                        # Track processed
                        self.processed_events.add(message_id)
                        if len(self.processed_events) > self.max_processed_cache:
                            # Remove oldest entries
                            to_remove = list(self.processed_events)[:1000]
                            for item in to_remove:
                                self.processed_events.discard(item)
                
            except Exception as e:
                logger.error("Error processing events", error=str(e))
                await asyncio.sleep(1)

    async def _handle_event(self, event_data: Dict[str, Any]):
        """Handle a single event."""
        # Parse event data (Redis stores everything as strings)
        event = {}
        for k, v in event_data.items():
            if k == "metadata":
                try:
                    event[k] = json.loads(v) if v else {}
                except Exception:
                    event[k] = {}
            elif k == "confidence":
                event[k] = float(v) if v else 0.9
            elif k == "re_entry":
                event[k] = v.lower() == "true" if v else False
            else:
                event[k] = v
        
        event_type = event.get("event_type")
        person_id = event.get("person_id")
        person_type = event.get("person_type", "CUSTOMER")
        session_id = event.get("session_id")
        timestamp_str = event.get("timestamp")
        
        # Parse timestamp
        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace("+05:30", "+05:30"))
        except Exception:
            timestamp = datetime.now(timezone(timedelta(hours=5, minutes=30)))
        
        # Write event to database
        await self.db_writer.write_event(event)
        
        # Skip session tracking for STAFF
        if person_type == "STAFF":
            logger.debug("Skipping session for STAFF", person_id=person_id)
            return
        
        # Get or create session
        session = await self.session_store.get_active_session(person_id)
        
        if not session and event_type == "ENTRY":
            # Create new session
            group_id = event.get("group_id")
            session = await self.session_store.create_session(
                person_id=person_id,
                timestamp=timestamp,
                session_id=session_id,
                group_id=group_id
            )
            session.person_type = person_type
            logger.info("New session created", session_id=session_id, person_id=person_id)
        
        if session:
            # Process event through state machine
            new_state = session.transition(event)
            await self.session_store.update_session(session)
            
            # Check if session is complete
            if session.is_terminal():
                await self.session_store.close_session(session)
                logger.info(
                    "Session closed",
                    session_id=session.session_id,
                    final_state=new_state.value,
                    dwell_seconds=session.dwell_seconds
                )

    async def _anomaly_detection_loop(self):
        """Periodically check for anomalies."""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                await self.anomaly_engine.check_all_anomalies()
            except Exception as e:
                logger.error("Error in anomaly detection", error=str(e))

    async def stop(self):
        """Stop the consumer service."""
        logger.info("Stopping ConsumerService")
        
        if self.session_store:
            await self.session_store.close()
        if self.anomaly_engine:
            await self.anomaly_engine.close()
        if self.db_writer:
            await self.db_writer.close()
        if self.redis:
            await self.redis.close()


async def main():
    """Entry point for consumer service."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    
    service = ConsumerService()
    
    try:
        await service.start()
    except KeyboardInterrupt:
        pass
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
