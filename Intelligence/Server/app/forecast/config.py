"""
Forecast plugin configuration — separate from core server settings.

All values can be overridden via environment variables with NAVOS_FORECAST_ prefix.
"""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class ForecastSettings(BaseSettings):
    """Configuration for the forecast plugin."""

    # Storage
    STORAGE_DIR: Path = Path("./data/forecast")
    RETENTION_HOURS: int = 48
    MAX_FILE_SIZE_MB: float = 10.0

    # Forecasting
    DEFAULT_HORIZON_MINUTES: int = 60
    DEFAULT_SAMPLING_INTERVAL_MINUTES: int = 5
    MIN_HISTORY_POINTS: int = 12  # At least ~1 hour at 5-min intervals
    MAX_AR_ORDER: int = 6  # Maximum autoregressive lag
    TREND_THRESHOLD: float = 0.5  # µg/m³ per step to call rising/falling

    # Channels
    PM_CHANNELS: list[str] = ["PM1_0", "PM2_5", "PM10"]

    model_config = SettingsConfigDict(
        env_prefix="NAVOS_FORECAST_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


_forecast_settings: ForecastSettings | None = None


def get_forecast_settings() -> ForecastSettings:
    global _forecast_settings
    if _forecast_settings is None:
        _forecast_settings = ForecastSettings()
    return _forecast_settings


def reset_forecast_settings() -> None:
    """For testing — force re-creation of settings."""
    global _forecast_settings
    _forecast_settings = None
