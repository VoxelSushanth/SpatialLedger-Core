"""Configuration for ingestion service."""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class IngestionConfig(BaseSettings):
    """Ingestion service configuration."""

    # PostgreSQL
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "store_intelligence"
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"

    # Redis
    redis_host: str = "redis"
    redis_port: int = 6379

    # Store
    store_id: str = "ST1008"
    store_name: str = "Brigade_Bangalore"

    # Video/Simulation
    video_path: str = "/data/videos"
    simulation_mode: str = "auto"  # auto, true, false
    yolo_model: str = "yolov8n.pt"
    tripwire_y_ratio: float = 0.15

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_prefix = ""
        case_sensitive = False

    @property
    def postgres_url(self) -> str:
        return f"postgresql://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}"

    def is_simulation_mode(self) -> bool:
        """Determine if running in simulation mode."""
        if self.simulation_mode.lower() == "true":
            return True
        if self.simulation_mode.lower() == "false":
            return False
        # Auto mode: check if video directory exists and has video files
        if not os.path.exists(self.video_path):
            return True
        video_extensions = {".mp4", ".avi", ".mov", ".mkv"}
        for f in os.listdir(self.video_path):
            if any(f.lower().endswith(ext) for ext in video_extensions):
                return False
        return True


@lru_cache()
def get_config() -> IngestionConfig:
    """Get cached config instance."""
    return IngestionConfig()
