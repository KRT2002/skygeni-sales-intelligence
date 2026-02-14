"""
config.py
---------
Centralised settings using Pydantic BaseSettings.
Reads from environment variables / .env file automatically.

Usage:
    from src.config import settings
    api_key = settings.groq_api_key
"""

import os
from pathlib import Path


def _load_dotenv():
    """Minimal .env loader — used when python-dotenv is not installed."""
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().upper()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


try:
    from pydantic import Field
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(
            env_file=".env",
            env_file_encoding="utf-8",
            case_sensitive=False,
            extra="ignore",
        )
        groq_api_key: str = Field(default="", description="Groq API key")
        model_name: str = Field(default="llama-3.3-70b-versatile")
        temperature: float = Field(default=0.5, ge=0.0, le=1.0)

        @property
        def llm_available(self) -> bool:
            return bool(self.groq_api_key.strip())

    settings = Settings()

except ImportError:
    # Fallback when pydantic-settings is not installed
    _load_dotenv()

    class _Settings:
        groq_api_key: str = os.environ.get("GROQ_API_KEY", "")
        model_name: str   = os.environ.get("MODEL_NAME", "llama-3.3-70b-versatile")
        temperature: float = float(os.environ.get("TEMPERATURE", "0.5"))

        @property
        def llm_available(self) -> bool:
            return bool(self.groq_api_key.strip())

    settings = _Settings()