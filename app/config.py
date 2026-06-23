from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash-lite"
    db_path: str = "vocab.db"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
