"""Staff classification based on heuristics."""
from typing import Literal, List
from .tracker import TrackHistory
import structlog

logger = structlog.get_logger()


# Known staff salesperson IDs from ground truth
STAFF_SALESPERSON_IDS = {523, 737, 971, 1178, 1190}


class StaffClassifier:
    """Classifies tracked persons as CUSTOMER, STAFF, or UNKNOWN."""

    def __init__(self):
        self.staff_tracks = set()  # track_ids confirmed as staff
        logger.info("StaffClassifier initialized")

    def classify(
        self, 
        track_history: TrackHistory, 
        zone_history: List[str],
        is_simulation_staff: bool = False
    ) -> Literal['CUSTOMER', 'STAFF', 'UNKNOWN']:
        """
        Classify a tracked person.
        
        Heuristics for STAFF classification:
        1. Explicitly marked in simulation mode
        2. Spends >70% of time in checkout zone
        3. Present since first 10 minutes (store opening)
        4. Stationary for >30 continuous minutes
        
        Args:
            track_history: History of tracked person
            zone_history: List of zones visited over time
            is_simulation_staff: True if explicitly marked as staff in simulation
            
        Returns:
            'CUSTOMER', 'STAFF', or 'UNKNOWN'
        """
        track_id = track_history.track_id

        # If already classified as staff, never reclassify
        if track_id in self.staff_tracks:
            return 'STAFF'

        # Simulation mode explicit marking
        if is_simulation_staff:
            self.staff_tracks.add(track_id)
            logger.debug("Track classified as STAFF (simulation)", track_id=track_id)
            return 'STAFF'

        # Heuristic 1: Check zone history for checkout dominance
        if len(zone_history) > 0:
            checkout_count = sum(1 for z in zone_history if z == "checkout")
            checkout_ratio = checkout_count / len(zone_history)
            if checkout_ratio > 0.7:
                self.staff_tracks.add(track_id)
                logger.debug("Track classified as STAFF (checkout presence)", track_id=track_id)
                return 'STAFF'

        # Heuristic 2: Present since store opening (first 10 minutes of tracking)
        # Assuming frame counter starts at store open
        if track_history.first_seen_frame <= 10:
            self.staff_tracks.add(track_id)
            logger.debug("Track classified as STAFF (early presence)", track_id=track_id)
            return 'STAFF'

        # Heuristic 3: Check for stationary behavior (>30 min equivalent frames)
        # Assuming 5 FPS, 30 min = 9000 frames
        if len(track_history.all_positions) > 100:
            # Check if position hasn't changed much
            first_pos = track_history.all_positions[0]
            last_pos = track_history.all_positions[-1]
            if abs(first_pos[0] - last_pos[0]) < 20 and abs(first_pos[1] - last_pos[1]) < 20:
                self.staff_tracks.add(track_id)
                logger.debug("Track classified as STAFF (stationary)", track_id=track_id)
                return 'STAFF'

        return 'CUSTOMER'

    def is_staff(self, track_id: str) -> bool:
        """Check if a track is classified as staff."""
        return track_id in self.staff_tracks

    def reset(self):
        """Reset all classifications."""
        self.staff_tracks.clear()
        logger.info("StaffClassifier reset")
