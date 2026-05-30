"""Tripwire crossing detection for entry/exit events."""
from typing import Optional, Literal, Dict
from .tracker import TrackHistory
import structlog

logger = structlog.get_logger()


class TripwireDetector:
    """Detects when tracked persons cross a virtual tripwire line."""

    def __init__(self, y_ratio: float = 0.15, debounce_seconds: int = 30):
        """
        Initialize tripwire detector.
        
        Args:
            y_ratio: Y position of tripwire as ratio of frame height (0.0-1.0)
            debounce_seconds: Minimum time between crossings for same track
        """
        self.y_ratio = y_ratio
        self.debounce_seconds = debounce_seconds
        self.last_crossing: Dict[str, float] = {}  # track_id -> last crossing timestamp
        logger.info("TripwireDetector initialized", y_ratio=y_ratio)

    def check_crossing(
        self, 
        track_history: TrackHistory, 
        frame_height: int,
        current_timestamp: float
    ) -> Optional[Literal['ENTRY', 'EXIT']]:
        """
        Check if track crossed the tripwire.
        
        ENTRY: centroid crosses tripwire top→bottom (entering store)
        EXIT: centroid crosses tripwire bottom→top (exiting store)
        
        Args:
            track_history: History of tracked person
            frame_height: Height of video frame
            current_timestamp: Current timestamp for debounce check
            
        Returns:
            'ENTRY', 'EXIT', or None
        """
        track_id = track_history.track_id
        
        # Debounce check
        if track_id in self.last_crossing:
            if current_timestamp - self.last_crossing[track_id] < self.debounce_seconds:
                return None

        # Need at least 2 positions to detect crossing
        if len(track_history.centroids) < 2:
            return None

        tripwire_y = frame_height * self.y_ratio
        
        # Get last two centroids
        prev_cx, prev_cy = track_history.centroids[-2]
        curr_cx, curr_cy = track_history.centroids[-1]

        # Check for ENTRY: crossing from above tripwire to below (top→bottom)
        if prev_cy < tripwire_y and curr_cy >= tripwire_y:
            self.last_crossing[track_id] = current_timestamp
            logger.debug("ENTRY detected", track_id=track_id)
            return 'ENTRY'

        # Check for EXIT: crossing from below tripwire to above (bottom→top)
        if prev_cy >= tripwire_y and curr_cy < tripwire_y:
            self.last_crossing[track_id] = current_timestamp
            logger.debug("EXIT detected", track_id=track_id)
            return 'EXIT'

        return None

    def reset(self):
        """Reset all state."""
        self.last_crossing.clear()
        logger.info("TripwireDetector reset")
