from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application configuration loaded from environment variables when available."""

    arxiv_categories: List[str] | str = ["cs.DC", "cs.OS", "cs.AR"]
    max_results_per_category: int = 25
    refresh_interval_minutes: int = 180  # deprecated
    refresh_hour: int = 8
    refresh_minute: int = 0
    scheduler_timezone: str = "Asia/Shanghai"
    database_url: str = "sqlite:///./papers.sqlite3"
    llm_api_key: str | None = None
    llm_model: str = "qwen-plus"
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    summary_sentence_count: int = 5
    summary_language: str = "zh"
    admin_token: str | None = None
    scheduler_enabled: bool = True
    request_timeout_seconds: int = 20
    full_text_chunk_chars: int = 6000
    full_text_chunk_overlap: int = 500
    full_text_max_chunks: int = 6
    sqlite_busy_timeout_seconds: int = 30
    sqlite_journal_mode: str = "WAL"

    model_config = SettingsConfigDict(
        env_file=str(_ROOT_DIR / ".env"),
        env_file_encoding="utf-8",
        env_prefix="PAPER_",
        extra="ignore",
    )

    @field_validator("arxiv_categories", mode="before")
    @classmethod
    def _split_categories(cls, value: str | List[str] | None) -> List[str]:
        if value is None:
            return ["cs.DC", "cs.OS", "cs.AR"]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
