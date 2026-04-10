"""
app/config.py
Application-wide configuration using pydantic-settings.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Aegis MediaGuard"
    version: str = "0.1.0"
    debug: bool = False

    # Matching thresholds
    fingerprint_match_threshold: float = 0.75
    watermark_confidence_boost: float = 0.20
    high_confidence_threshold: float = 0.80

    # Sandbox
    sandbox_timeout_seconds: int = 10

    # Scoring
    urgent_live_leak_min_score: int = 85
    suspected_infringement_min_score: int = 55

    model_config = {"env_prefix": "AEGIS_"}


settings = Settings()
