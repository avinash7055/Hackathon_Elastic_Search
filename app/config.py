"""Centralized configuration loaded from environment variables."""

from pathlib import Path
from pydantic_settings import BaseSettings
from functools import lru_cache


# Resolve .env relative to project root (parent of app/)
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    """Application settings from .env file."""

    # Elastic Cloud Serverless
    elasticsearch_url: str = "http://localhost:9200"
    elasticsearch_api_key: str = ""

    kibana_url: str = "http://localhost:5601"
    kibana_api_key: str = ""

    # LLM (optional, for local summarization)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # App settings
    log_level: str = "INFO"
    faers_record_count: int = 500_000

    model_config = {
        "env_file": str(ENV_FILE),
        "env_file_encoding": "utf-8",
        "extra": "ignore",  # Don't error on unexpected env vars
    }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
