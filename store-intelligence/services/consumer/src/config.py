"""Configuration for consumer service."""
import os
from functools import lru_cache
from pydantic_settings import BaseSettings


class ConsumerConfig(BaseSettings):
    """Consumer service configuration."""

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


@lru_cache()
def get_config() -> ConsumerConfig:
    """Get cached config instance."""
    return ConsumerConfig()
