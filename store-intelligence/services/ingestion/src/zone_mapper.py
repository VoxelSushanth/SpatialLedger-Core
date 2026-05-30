"""Zone mapping for store layout."""
from typing import Dict, Tuple, List
import structlog

logger = structlog.get_logger()


# Store layout for Brigade Road Bangalore
# Zones defined as proportional rectangles (x, y, width, height) in 0.0-1.0 coordinates
ZONE_DEFINITIONS = {
    "entrance":      {"x": 0.35, "y": 0.0,  "w": 0.30, "h": 0.15},
    "makeup":        {"x": 0.0,  "y": 0.15, "w": 0.40, "h": 0.45},
    "skincare":      {"x": 0.40, "y": 0.15, "w": 0.30, "h": 0.35},
    "hair":          {"x": 0.70, "y": 0.15, "w": 0.30, "h": 0.35},
    "fragrance":     {"x": 0.60, "y": 0.50, "w": 0.40, "h": 0.25},
    "personal_care": {"x": 0.0,  "y": 0.60, "w": 0.30, "h": 0.25},
    "checkout":      {"x": 0.30, "y": 0.75, "w": 0.40, "h": 0.25},
}

ZONE_DISPLAY_NAMES = {
    "entrance": "Entrance",
    "makeup": "Makeup",
    "skincare": "Skincare",
    "hair": "Hair",
    "fragrance": "Fragrance",
    "personal_care": "Personal Care",
    "checkout": "Checkout",
    "unknown": "Unknown",
}


class ZoneMapper:
    """Maps bounding boxes to store zones."""

    def __init__(self):
        self.zone_definitions = ZONE_DEFINITIONS
        logger.info("ZoneMapper initialized", zones=list(ZONE_DEFINITIONS.keys()))

    def get_zone(self, bbox: Tuple[int, int, int, int], frame_w: int, frame_h: int) -> str:
        """
        Determine which zone contains the centroid of a bounding box.
        
        Args:
            bbox: (x1, y1, x2, y2) bounding box
            frame_w: Frame width
            frame_h: Frame height
            
        Returns:
            zone_id string
        """
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2

        # Normalize to 0.0-1.0
        nx = cx / frame_w
        ny = cy / frame_h

        # Check each zone
        for zone_id, zone_def in self.zone_definitions.items():
            zx = zone_def["x"]
            zy = zone_def["y"]
            zw = zone_def["w"]
            zh = zone_def["h"]

            if (zx <= nx < zx + zw) and (zy <= ny < zy + zh):
                return zone_id

        return "unknown"

    def get_all_zones(self) -> List[str]:
        """Get list of all zone IDs."""
        return list(self.zone_definitions.keys())

    def get_zone_display_name(self, zone_id: str) -> str:
        """Get display name for a zone."""
        return ZONE_DISPLAY_NAMES.get(zone_id, zone_id.title())

    def is_product_zone(self, zone_id: str) -> bool:
        """Check if zone is a product browsing zone (not entrance/checkout)."""
        product_zones = {"makeup", "skincare", "hair", "fragrance", "personal_care"}
        return zone_id in product_zones
