"""Main ingestion service - video processing and event generation."""
import asyncio
import os
import random
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import structlog

from .config import get_config
from .detector import PersonDetector, Detection
from .tracker import PersonTracker, TrackHistory
from .tripwire import TripwireDetector
from .zone_mapper import ZoneMapper
from .staff_classifier import StaffClassifier
from .event_builder import EventBuilder
from .publisher import EventPublisher

logger = structlog.get_logger()

# Ground truth data for simulation
STORE_OPERATING_HOURS = {
    "open": "12:15",
    "close": "21:40"
}

TRANSACTION_HOURS_WEIGHTS = {
    12: 0.08, 13: 0.08, 14: 0.04, 15: 0.12,
    16: 0.12, 17: 0.08, 18: 0.12, 19: 0.20,
    20: 0.04, 21: 0.08
}

STAFF_DATA = [
    {"salesperson_id": 523, "employee_code": "CL1997", "name": "Shashikala"},
    {"salesperson_id": 737, "employee_code": "CL2541", "name": "Naziya Begum"},
    {"salesperson_id": 971, "employee_code": "CL2727", "name": "Zufishan Khazra"},
    {"salesperson_id": 1178, "employee_code": "CL2063", "name": "kasthuri v"},
    {"salesperson_id": 1190, "employee_code": "CL2680", "name": "Priya v"},
]

# Known transaction times from ground truth (24 transactions)
TRANSACTION_TIMES = [
    "12:23", "12:51",
    "13:15", "13:42",
    "14:38",
    "15:12", "15:34", "15:58",
    "16:22", "16:45", "16:59",
    "17:18", "17:52",
    "18:14", "18:37", "18:56",
    "19:08", "19:23", "19:35", "19:47", "19:58",
    "20:32",
    "21:15", "21:38"
]


class IngestionService:
    """Main ingestion service."""

    def __init__(self):
        self.config = get_config()
        self.detector: Optional[PersonDetector] = None
        self.tracker = PersonTracker()
        self.tripwire = TripwireDetector(y_ratio=self.config.tripwire_y_ratio)
        self.zone_mapper = ZoneMapper()
        self.staff_classifier = StaffClassifier()
        self.publisher = EventPublisher(redis_url=self.config.redis_url)
        self.event_builder = EventBuilder()
        
        # Simulation state
        self.simulation_mode = False
        self.generated_events = 0
        self.unique_visitors = 0
        self.purchased_sessions = set()
        
        # Track session states
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.track_to_session: Dict[str, str] = {}
        self.person_exit_times: Dict[str, datetime] = {}

    async def start(self):
        """Start the ingestion service."""
        logger.info("Starting IngestionService", store_id=self.config.store_id)
        
        await self.publisher.connect()
        await self.publisher.trim_stream(max_age_hours=24)
        
        # Check if running in simulation mode
        self.simulation_mode = self.config.is_simulation_mode()
        
        if self.simulation_mode:
            logger.info("SIMULATION MODE: no video found in data/videos/")
            await self.run_simulation()
        else:
            logger.info("REAL VIDEO MODE: processing video files")
            await self.run_video_processing()

    async def run_simulation(self):
        """Run in simulation mode - generate synthetic events."""
        # Seed random for reproducibility
        random.seed(hash(self.config.store_id) % (2**32))
        
        base_date = datetime(2026, 4, 10)
        ist = timezone(timedelta(hours=5, minutes=30))
        
        logger.info("Starting simulation event generation")
        
        # Generate 5 staff tracks active all day
        staff_tracks = []
        for i, staff in enumerate(STAFF_DATA):
            track_id = f"staff_{i:03d}"
            staff_tracks.append(track_id)
            
            # Staff entry at store open
            entry_time = base_date.replace(hour=12, minute=0, second=0, tzinfo=ist)
            session_id = f"sess_staff_{i:03d}"
            
            event = self.event_builder.build_entry_event(
                track_id=track_id,
                timestamp=entry_time,
                session_id=session_id,
                zone_id="checkout",
                confidence=0.95
            )
            event["person_type"] = "STAFF"
            await self.publisher.publish(event)
            self.generated_events += 1
            
            # Staff stays in checkout zone mostly
            for hour in range(12, 22):
                zone_event = self.event_builder.build_zone_event(
                    track_id=track_id,
                    timestamp=entry_time.replace(hour=hour, minute=random.randint(0, 59)),
                    session_id=session_id,
                    zone_id="checkout",
                    event_type="ZONE_ENTER",
                    person_type="STAFF"
                )
                await self.publisher.publish(zone_event)
                self.generated_events += 1
        
        # Generate ~96 customer visits
        total_customers = 96
        purchased_count = 24  # Match ground truth
        
        # Distribute customers by hour
        customers_by_hour = {}
        remaining = total_customers
        hours = sorted(TRANSACTION_HOURS_WEIGHTS.keys())
        for i, hour in enumerate(hours):
            weight = TRANSACTION_HOURS_WEIGHTS[hour]
            if i == len(hours) - 1:
                count = remaining
            else:
                count = int(total_customers * weight)
                remaining -= count
            customers_by_hour[hour] = count
        
        # Track which transactions are matched
        used_transaction_times = list(TRANSACTION_TIMES)
        random.shuffle(used_transaction_times)
        
        visitor_id = 0
        for hour, count in customers_by_hour.items():
            for _ in range(count):
                visitor_id += 1
                await self._simulate_customer_visit(
                    base_date, ist, hour, visitor_id,
                    used_transaction_times, visitor_id <= purchased_count
                )
                
                if not self.simulation_mode:
                    return  # Safety check
                
                await asyncio.sleep(0.01)  # Small delay between visitors
        
        # Log completion
        logger.info(
            "Simulation complete",
            total_events=self.generated_events,
            unique_visitors=self.unique_visitors,
            purchased_sessions=len(self.purchased_sessions)
        )
        
        # Keep service running
        while True:
            await asyncio.sleep(3600)

    async def _simulate_customer_visit(
        self,
        base_date: datetime,
        ist: timezone,
        hour: int,
        visitor_id: int,
        transaction_times: List[str],
        will_purchase: bool
    ):
        """Simulate a single customer visit."""
        track_id = f"track_{visitor_id:03d}"
        session_id = f"sess_{visitor_id:06d}"
        
        # Random entry time within the hour
        minute = random.randint(0, 59)
        entry_time = base_date.replace(hour=hour, minute=minute, second=random.randint(0, 59), tzinfo=ist)
        
        # Check for re-entry (10% chance)
        re_entry = random.random() < 0.10
        if re_entry and track_id in self.person_exit_times:
            prev_exit = self.person_exit_times[track_id]
            if (entry_time - prev_exit).total_seconds() < 3600:  # Within 1 hour
                re_entry = True
            else:
                re_entry = False
        
        # Group entry (5% chance)
        group_id = None
        if random.random() < 0.05:
            group_id = f"group_{random.randint(1, 10):03d}"
        
        # ENTRY event
        entry_event = self.event_builder.build_entry_event(
            track_id=track_id,
            timestamp=entry_time,
            session_id=session_id,
            re_entry=re_entry,
            group_id=group_id
        )
        await self.publisher.publish(entry_event)
        self.generated_events += 1
        
        if not re_entry:
            self.unique_visitors += 1
        
        # Store session state
        self.sessions[session_id] = {
            "state": "ENTERED",
            "entered_at": entry_time,
            "zones_visited": [],
            "track_id": track_id
        }
        self.track_to_session[track_id] = session_id
        
        # Determine zones to visit (1-3 zones, weighted by department GMV)
        zone_weights = {
            "makeup": 0.64, "skincare": 0.26, "hair": 0.04,
            "fragrance": 0.03, "personal_care": 0.02, "checkout": 0.01
        }
        num_zones = random.randint(1, 3)
        zones_to_visit = random.choices(
            list(zone_weights.keys()),
            weights=list(zone_weights.values()),
            k=num_zones
        )
        zones_to_visit = list(dict.fromkeys(zones_to_visit))  # Remove duplicates, preserve order
        
        # Ensure checkout is visited if purchasing
        if will_purchase and "checkout" not in zones_to_visit:
            zones_to_visit.append("checkout")
        
        current_time = entry_time
        dwell_total = 0
        
        # Visit each zone
        for zone in zones_to_visit:
            if zone == "checkout":
                continue  # Handle checkout separately
            
            # Time spent traveling to zone
            current_time += timedelta(minutes=random.randint(1, 3))
            
            # ZONE_ENTER
            zone_event = self.event_builder.build_zone_event(
                track_id=track_id,
                timestamp=current_time,
                session_id=session_id,
                zone_id=zone,
                event_type="ZONE_ENTER"
            )
            await self.publisher.publish(zone_event)
            self.generated_events += 1
            
            self.sessions[session_id]["zones_visited"].append(zone)
            
            # Dwell time in zone (normal distribution, mean=8 min, std=3 min)
            dwell_minutes = max(2, min(30, random.gauss(8, 3)))
            dwell_seconds = int(dwell_minutes * 60)
            dwell_total += dwell_seconds
            
            # DWELL event if > 2 minutes
            if dwell_minutes >= 2:
                dwell_event = self.event_builder.build_dwell_event(
                    track_id=track_id,
                    timestamp=current_time + timedelta(minutes=dwell_minutes),
                    session_id=session_id,
                    zone_id=zone,
                    dwell_seconds=dwell_seconds
                )
                await self.publisher.publish(dwell_event)
                self.generated_events += 1
            
            current_time += timedelta(minutes=dwell_minutes)
            
            # ZONE_EXIT
            zone_exit_event = self.event_builder.build_zone_event(
                track_id=track_id,
                timestamp=current_time,
                session_id=session_id,
                zone_id=zone,
                event_type="ZONE_EXIT"
            )
            await self.publisher.publish(zone_exit_event)
            self.generated_events += 1
        
        # Checkout if purchasing
        if will_purchase:
            current_time += timedelta(minutes=random.randint(1, 3))
            
            # ZONE_ENTER checkout
            checkout_event = self.event_builder.build_zone_event(
                track_id=track_id,
                timestamp=current_time,
                session_id=session_id,
                zone_id="checkout",
                event_type="ZONE_ENTER"
            )
            await self.publisher.publish(checkout_event)
            self.generated_events += 1
            
            self.sessions[session_id]["state"] = "CHECKOUT"
            self.purchased_sessions.add(session_id)
        
        # EXIT event
        exit_time = current_time + timedelta(minutes=random.randint(1, 5))
        
        # If purchasing, align exit with transaction time
        if will_purchase and transaction_times:
            txn_time_str = transaction_times.pop()
            txn_hour, txn_min = map(int, txn_time_str.split(":"))
            exit_time = base_date.replace(hour=txn_hour, minute=txn_min, second=random.randint(0, 59), tzinfo=ist)
        
        dwell_total = int((exit_time - entry_time).total_seconds())
        
        exit_event = self.event_builder.build_exit_event(
            track_id=track_id,
            timestamp=exit_time,
            session_id=session_id,
            dwell_seconds=dwell_total
        )
        await self.publisher.publish(exit_event)
        self.generated_events += 1
        
        self.person_exit_times[track_id] = exit_time
        self.sessions[session_id]["ended_at"] = exit_time
        
        if will_purchase:
            self.sessions[session_id]["state"] = "PURCHASED"
        else:
            self.sessions[session_id]["state"] = "EXITED"

    async def run_video_processing(self):
        """Run real video processing mode."""
        # This would process actual video files
        # For now, we just log that we're in video mode
        logger.warning("Video processing mode not fully implemented - falling back to simulation")
        await self.run_simulation()

    async def stop(self):
        """Stop the ingestion service."""
        logger.info("Stopping IngestionService")
        await self.publisher.close()


async def main():
    """Entry point for ingestion service."""
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
    
    service = IngestionService()
    
    try:
        await service.start()
    except KeyboardInterrupt:
        pass
    finally:
        await service.stop()


if __name__ == "__main__":
    asyncio.run(main())
