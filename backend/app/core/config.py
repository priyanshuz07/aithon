from functools import lru_cache
import os
from secrets import token_urlsafe

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Behavior Firewall 2.0"
    app_env: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: str = Field(
        default_factory=lambda: "sqlite:////tmp/behavior_firewall.db"
        if os.getenv("VERCEL") == "1"
        else "sqlite:///../data/behavior_firewall.db"
    )
    ml_model_path: str | None = None
    data_retention_enabled: bool = True
    data_retention_days: int = Field(default=90, ge=1, le=3650)
    risk_medium_threshold: int = Field(default=30, ge=1, le=98)
    risk_high_threshold: int = Field(default=60, ge=2, le=99)
    risk_critical_threshold: int = Field(default=80, ge=3, le=100)
    safe_demo_mode: bool = True
    adaptive_delay_ms: int = Field(default=2500, ge=0, le=30_000)
    demo_challenge_ttl_seconds: int = Field(default=300, ge=30, le=1800)
    demo_challenge_secret: str = Field(default_factory=lambda: token_urlsafe(32), min_length=32)
    admin_api_key: str | None = Field(default=None, min_length=24)
    cors_origins: list[str] = [
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:5501",
        "http://127.0.0.1:5501",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_risk_threshold_order(self) -> "Settings":
        if not self.risk_medium_threshold < self.risk_high_threshold < self.risk_critical_threshold:
            raise ValueError("Risk thresholds must be strictly increasing")
        if not self.safe_demo_mode:
            raise ValueError("This prototype supports safe demo mode only")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
