"""ByteTrack-based person tracker."""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import numpy as np
import structlog

logger = structlog.get_logger()


@dataclass
class TrackedPerson:
    """Tracked person result."""
    track_id: str
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)
    confidence: float
    frames_tracked: int


@dataclass
class TrackHistory:
    """History of a tracked person."""
    track_id: str
    first_seen_frame: int
    last_seen_frame: int
    all_positions: List[Tuple[int, int, int, int]] = field(default_factory=list)
    centroids: List[Tuple[float, float]] = field(default_factory=list)


class PersonTracker:
    """ByteTrack wrapper for person tracking."""

    def __init__(self):
        self.track_registry: Dict[str, TrackHistory] = {}
        self.frame_counter = 0
        logger.info("PersonTracker initialized")

    def update(self, detections: List, frame: np.ndarray) -> List[TrackedPerson]:
        """
        Update tracks with new detections.
        
        In simulation mode, detections already have track_ids.
        In real video mode, we'd use ByteTrack here.
        
        Args:
            detections: List of Detection objects (may have track_id set)
            frame: Current frame
            
        Returns:
            List of TrackedPerson objects
        """
        self.frame_counter += 1
        tracked = []

        for det in detections:
            # If detection already has track_id (simulation mode), use it
            if hasattr(det, 'track_id') and det.track_id:
                track_id = det.track_id
            else:
                # Generate new track_id for new detections
                track_id = f"track_{len(self.track_registry):03d}"

            # Update or create track history
            if track_id not in self.track_registry:
                self.track_registry[track_id] = TrackHistory(
                    track_id=track_id,
                    first_seen_frame=self.frame_counter,
                    last_seen_frame=self.frame_counter,
                    all_positions=[det.bbox],
                )
                # Calculate centroid
                x1, y1, x2, y2 = det.bbox
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                self.track_registry[track_id].centroids = [(cx, cy)]
            else:
                history = self.track_registry[track_id]
                history.last_seen_frame = self.frame_counter
                history.all_positions.append(det.bbox)
                x1, y1, x2, y2 = det.bbox
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                history.centroids.append((cx, cy))

            tracked_person = TrackedPerson(
                track_id=track_id,
                bbox=det.bbox,
                confidence=det.confidence,
                frames_tracked=self.frame_counter - self.track_registry[track_id].first_seen_frame + 1
            )
            tracked.append(tracked_person)

        return tracked

    def get_track_history(self, track_id: str) -> Optional[TrackHistory]:
        """Get history for a specific track."""
        return self.track_registry.get(track_id)

    def get_all_active_tracks(self) -> List[str]:
        """Get all currently active track IDs."""
        return list(self.track_registry.keys())
