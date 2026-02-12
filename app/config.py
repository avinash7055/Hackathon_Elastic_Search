"""Centralized configuration loaded from environment variables."""

from pydantic_settings import BaseSettings
from functools import lru_cache


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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
