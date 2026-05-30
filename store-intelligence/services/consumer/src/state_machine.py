"""Session state machine for tracking customer journey."""
from enum import Enum
from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog

logger = structlog.get_logger()


class PersonState(Enum):
    """Possible states for a person session."""
    ENTERED = "ENTERED"
    BROWSING = "BROWSING"
    ENGAGED = "ENGAGED"
    CHECKOUT = "CHECKOUT"
    EXITED = "EXITED"
    PURCHASED = "PURCHASED"


# Product zones that trigger BROWSING state
PRODUCT_ZONES = {"makeup", "skincare", "hair", "fragrance", "personal_care"}


class SessionStateMachine:
    """State machine for tracking a customer's journey through the store."""

    def __init__(self, session_id: str, person_id: str, started_at: datetime):
        self.session_id = session_id
        self.person_id = person_id
        self.started_at = started_at
        self.state = PersonState.ENTERED
        self.ended_at: Optional[datetime] = None
        self.zones_visited: List[str] = []
        self.zone_enter_times: Dict[str, datetime] = {}
        self.dwell_seconds: int = 0
        self.re_entry: bool = False
        self.group_id: Optional[str] = None
        self.person_type: str = "CUSTOMER"
        self.events: List[Dict[str, Any]] = []
        
        logger.debug("SessionStateMachine created", session_id=session_id)

    def transition(self, event: Dict[str, Any]) -> PersonState:
        """
        Process an event and transition state accordingly.
        
        Args:
            event: Event dict from ingestion
            
        Returns:
            New state after transition
        """
        event_type = event.get("event_type")
        zone_id = event.get("zone_id")
        timestamp_str = event.get("timestamp")
        
        # Parse timestamp
        try:
            timestamp = datetime.fromisoformat(timestamp_str.replace("+05:30", "+05:30"))
        except Exception:
            timestamp = datetime.now()
        
        self.events.append(event)
        
        # Handle re-entry
        if event.get("re_entry", False) and event_type == "ENTRY":
            self.re_entry = True
            logger.debug("Re-entry detected", session_id=self.session_id)
            return self.state
        
        # State transitions based on event type
        if event_type == "ZONE_ENTER":
            if zone_id and zone_id not in self.zones_visited:
                self.zones_visited.append(zone_id)
            self.zone_enter_times[zone_id] = timestamp
            
            if self.state == PersonState.ENTERED:
                if zone_id == "checkout":
                    self.state = PersonState.CHECKOUT
                elif zone_id in PRODUCT_ZONES:
                    self.state = PersonState.BROWSING
                    
            elif self.state == PersonState.BROWSING:
                if zone_id == "checkout":
                    self.state = PersonState.CHECKOUT
                    
            elif self.state == PersonState.ENGAGED:
                if zone_id == "checkout":
                    self.state = PersonState.CHECKOUT
        
        elif event_type == "ZONE_EXIT":
            # Calculate dwell time in this zone
            if zone_id and zone_id in self.zone_enter_times:
                enter_time = self.zone_enter_times[zone_id]
                dwell = (timestamp - enter_time).total_seconds()
                self.dwell_seconds += int(dwell)
                
                # Check for ENGAGED state (dwell > 120 seconds in product zone)
                if self.state == PersonState.BROWSING and dwell > 120 and zone_id in PRODUCT_ZONES:
                    self.state = PersonState.ENGAGED
        
        elif event_type == "DWELL":
            # Explicit dwell event
            dwell_seconds = event.get("metadata", {}).get("dwell_seconds", 0)
            if dwell_seconds > 120 and self.state == PersonState.BROWSING:
                self.state = PersonState.ENGAGED
        
        elif event_type == "EXIT":
            self.ended_at = timestamp
            
            # Update total dwell time from event metadata
            event_dwell = event.get("metadata", {}).get("dwell_seconds")
            if event_dwell:
                self.dwell_seconds = event_dwell
            
            # Determine final state
            if self.state == PersonState.CHECKOUT:
                self.state = PersonState.PURCHASED
            else:
                self.state = PersonState.EXITED
        
        logger.debug(
            "State transition",
            session_id=self.session_id,
            event_type=event_type,
            new_state=self.state.value
        )
        
        return self.state

    def is_terminal(self) -> bool:
        """Check if session is in a terminal state."""
        return self.state in (PersonState.EXITED, PersonState.PURCHASED)

    def to_dict(self) -> Dict[str, Any]:
        """Convert session to dictionary for storage."""
        return {
            "session_id": self.session_id,
            "person_id": self.person_id,
            "person_type": self.person_type,
            "state": self.state.value,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "dwell_seconds": self.dwell_seconds,
            "zones_visited": self.zones_visited,
            "re_entry": self.re_entry,
            "group_id": self.group_id,
        }

    def get_current_state(self) -> str:
        """Get current state as string."""
        return self.state.value
