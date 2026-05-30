"""YOLOv8 person detector."""
import numpy as np
from dataclasses import dataclass
from typing import List, Optional
from ultralytics import YOLO
import structlog

logger = structlog.get_logger()


@dataclass
class Detection:
    """Detection result for a person."""
    track_id: str
    bbox: tuple  # (x1, y1, x2, y2)
    confidence: float
    class_name: str


class PersonDetector:
    """YOLOv8-based person detector."""

    def __init__(self, model_path: str = "yolov8n.pt", confidence_threshold: float = 0.45):
        self.model = YOLO(model_path)
        self.confidence_threshold = confidence_threshold
        logger.info("PersonDetector initialized", model=model_path, threshold=confidence_threshold)

    def detect(self, frame: np.ndarray) -> List[Detection]:
        """
        Detect persons in a frame.
        
        Args:
            frame: BGR image as numpy array
            
        Returns:
            List of Detection objects for persons found
        """
        results = self.model(frame, verbose=False, conf=self.confidence_threshold)
        detections = []

        if len(results) == 0 or results[0].boxes is None:
            return detections

        boxes = results[0].boxes
        for i in range(len(boxes)):
            try:
                cls_id = int(boxes.cls[i])
                conf = float(boxes.conf[i])
                bbox_xyxy = boxes.xyxy[i].cpu().numpy()

                # COCO class 0 is 'person'
                if cls_id != 0:
                    continue

                detection = Detection(
                    track_id="",  # Will be set by tracker
                    bbox=tuple(map(int, bbox_xyxy)),
                    confidence=conf,
                    class_name="person"
                )
                detections.append(detection)
            except Exception as e:
                logger.warning("Error processing detection", error=str(e))

        return detections
