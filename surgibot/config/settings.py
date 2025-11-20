"""
Settings and configuration management using Pydantic.
Loads from environment variables with fallback defaults.
"""

import os
from pathlib import Path
from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ===================== API Server Settings =====================
    api_host: str = "0.0.0.0"
    api_port: int = 8088
    surgibot_secret: str = "uTCoBelMyNfSSNmUulT_Kz6zrrCVkvD578MxEuLKZoaaXX0pVlpAD8toYHBxsFxI"

    # ===================== Client Settings =====================
    client_host: str = "127.0.0.1"
    client_port: int = 8088
    client_purge_minutes: int = 3

    # ===================== TTS Settings =====================
    announce_minutes: int = 20
    postponed_repeat: int = 2
    postponed_gap_sec: int = 8
    bilingual_pause_ms: int = 600

    # ===================== Auto-transition Settings =====================
    auto_discharge_delay_min: int = 3
    auto_delete_after_discharge_min: int = 3
    recovery_duration_hours: int = 1

    # ===================== Google Sheets Settings =====================
    spreadsheet_id: str = "1dr6pCw8dEnCh_UYJXJzAFsthdZ8IsRBF3VlNw1AlvjI"
    gcp_credentials_json: Optional[str] = None
    gcp_credentials_file: Optional[str] = None
    embedded_credentials_json: Optional[str] = None

    # ===================== Database Settings =====================
    database_url: str = "sqlite:///./surgibot.db"
    database_echo: bool = False

    # ===================== Logging Settings =====================
    log_level: str = "INFO"
    log_file: Optional[str] = "surgibot.log"
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # ===================== Security Settings =====================
    cors_origins: list[str] = ["*"]
    token_expire_minutes: int = 43200  # 30 days

    # ===================== Features =====================
    enable_sheets: bool = True
    enable_tts: bool = True
    enable_auto_transitions: bool = True

    @property
    def base_url(self) -> str:
        """Get base URL for API server."""
        return f"http://{self.api_host}:{self.api_port}"

    @property
    def client_base_url(self) -> str:
        """Get base URL for client connection."""
        return f"http://{self.client_host}:{self.client_port}"

    def load_from_env(self) -> None:
        """Reload settings from environment variables."""
        # Map old environment variable names to new ones
        env_mapping = {
            "SURGIBOT_API_HOST": "api_host",
            "SURGIBOT_API_PORT": "api_port",
            "SURGIBOT_SECRET": "surgibot_secret",
            "SURGIBOT_CLIENT_HOST": "client_host",
            "SURGIBOT_CLIENT_PORT": "client_port",
            "SURGIBOT_ANNOUNCE_MINUTES": "announce_minutes",
            "SURGIBOT_AUTO_DELETE_MIN": "auto_delete_after_discharge_min",
            "SURGIBOT_SPREADSHEET_ID": "spreadsheet_id",
            "SURGIBOT_GCP_CREDENTIALS_JSON": "gcp_credentials_json",
            "SURGIBOT_GCP_CREDENTIALS_FILE": "gcp_credentials_file",
        }

        for env_key, attr_name in env_mapping.items():
            value = os.environ.get(env_key)
            if value is not None:
                setattr(self, attr_name, value)


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
