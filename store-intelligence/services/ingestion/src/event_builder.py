"""Event builder for creating standardized events."""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import structlog

logger = structlog.get_logger()

# IST timezone offset
IST_OFFSET = timezone.utc.replace()  # We'll use +05:30 manually


def get_ist_timestamp() -> str:
    """Get current timestamp in IST format."""
    from datetime import timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).isoformat()


def format_timestamp(dt: datetime) -> str:
    """Format datetime to ISO8601 with IST timezone."""
    from datetime import timedelta
    ist = timezone(timedelta(hours=5, minutes=30))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ist)
    else:
        dt = dt.astimezone(ist)
    return dt.isoformat()


class EventBuilder:
    """Builds events conforming to the standard event schema."""

    @staticmethod
    def build_entry_event(
        track_id: str,
        timestamp: Optional[datetime] = None,
        session_id: Optional[str] = None,
        camera_id: str = "cam_01",
        confidence: float = 0.9,
        re_entry: bool = False,
        group_id: Optional[str] = None,
        zone_id: str = "entrance"
    ) -> Dict[str, Any]:
        """Build an ENTRY event."""
        ts = timestamp or datetime.now()
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": "ENTRY",
            "timestamp": format_timestamp(ts),
            "person_id": track_id,
            "person_type": "CUSTOMER",
            "session_id": session_id or f"sess_{uuid.uuid4().hex[:12]}",
            "zone_id": zone_id,
            "camera_id": camera_id,
            "confidence": confidence,
            "re_entry": re_entry,
            "group_id": group_id,
            "metadata": {
                "bbox": None,
                "dwell_seconds": None,
                "frame_number": None
            }
        }

    @staticmethod
    def build_exit_event(
        track_id: str,
        timestamp: Optional[datetime] = None,
        session_id: Optional[str] = None,
        zone_id: str = "entrance",
        camera_id: str = "cam_01",
        dwell_seconds: Optional[int] = None,
        person_type: str = "CUSTOMER"
    ) -> Dict[str, Any]:
        """Build an EXIT event."""
        ts = timestamp or datetime.now()
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": "EXIT",
            "timestamp": format_timestamp(ts),
            "person_id": track_id,
            "person_type": person_type,
            "session_id": session_id,
            "zone_id": zone_id,
            "camera_id": camera_id,
            "confidence": 0.9,
            "re_entry": False,
            "group_id": None,
            "metadata": {
                "bbox": None,
                "dwell_seconds": dwell_seconds,
                "frame_number": None
            }
        }

    @staticmethod
    def build_zone_event(
        track_id: str,
        timestamp: Optional[datetime] = None,
        session_id: Optional[str] = None,
        zone_id: str = "makeup",
        event_type: str = "ZONE_ENTER",
        camera_id: str = "cam_01",
        confidence: float = 0.9,
        person_type: str = "CUSTOMER"
    ) -> Dict[str, Any]:
        """Build a ZONE_ENTER or ZONE_EXIT event."""
        ts = timestamp or datetime.now()
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "timestamp": format_timestamp(ts),
            "person_id": track_id,
            "person_type": person_type,
            "session_id": session_id,
            "zone_id": zone_id,
            "camera_id": camera_id,
            "confidence": confidence,
            "re_entry": False,
            "group_id": None,
            "metadata": {
                "bbox": None,
                "dwell_seconds": None,
                "frame_number": None
            }
        }

    @staticmethod
    def build_dwell_event(
        track_id: str,
        timestamp: Optional[datetime] = None,
        session_id: Optional[str] = None,
        zone_id: str = "makeup",
        dwell_seconds: int = 120,
        camera_id: str = "cam_01",
        confidence: float = 0.9,
        person_type: str = "CUSTOMER"
    ) -> Dict[str, Any]:
        """Build a DWELL event."""
        ts = timestamp or datetime.now()
        return {
            "event_id": str(uuid.uuid4()),
            "event_type": "DWELL",
            "timestamp": format_timestamp(ts),
            "person_id": track_id,
            "person_type": person_type,
            "session_id": session_id,
            "zone_id": zone_id,
            "camera_id": camera_id,
            "confidence": confidence,
            "re_entry": False,
            "group_id": None,
            "metadata": {
                "bbox": None,
                "dwell_seconds": dwell_seconds,
                "frame_number": None
            }
        }
