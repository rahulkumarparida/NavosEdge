from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core import constants

class Settings(BaseSettings):
    APP_NAME: str = constants.APP_NAME_DEFAULT
    APP_VERSION: str = constants.APP_VERSION_DEFAULT
    HOST: str = constants.HOST_DEFAULT
    PORT: int = constants.PORT_DEFAULT
    LOG_LEVEL: str = constants.LOG_LEVEL_DEFAULT
    DATA_DIR: Path = constants.DATA_DIR_DEFAULT
    ARTIFACTS_DIR: Path = constants.ARTIFACTS_DIR_DEFAULT
    MAX_PAYLOAD_BYTES: int = constants.MAX_PAYLOAD_BYTES_DEFAULT
    SSE_HEARTBEAT_INTERVAL_S: float = constants.SSE_HEARTBEAT_INTERVAL_S_DEFAULT
    STORAGE_MAX_FILE_SIZE_MB: float = constants.STORAGE_MAX_FILE_SIZE_MB_DEFAULT
    STORAGE_MAX_FILES_PER_NODE: int = constants.STORAGE_MAX_FILES_PER_NODE_DEFAULT
    MODEL_WEIGHTS_FILE: str = constants.MODEL_WEIGHTS_FILE_DEFAULT
    MODEL_PREPROCESS_FILE: str = constants.MODEL_PREPROCESS_FILE_DEFAULT

    # Anomaly detection engine
    ANOMALY_HISTORY_WINDOW_HOURS: int = constants.ANOMALY_HISTORY_WINDOW_HOURS_DEFAULT
    ANOMALY_MODEL_UPDATE_INTERVAL_MINUTES: int = constants.ANOMALY_MODEL_UPDATE_INTERVAL_MINUTES_DEFAULT
    ANOMALY_MIN_SAMPLES_FOR_REGRESSION: int = constants.ANOMALY_MIN_SAMPLES_FOR_REGRESSION_DEFAULT
    ANOMALY_MIN_SAMPLES_FOR_MONITORING: int = constants.ANOMALY_MIN_SAMPLES_FOR_MONITORING_DEFAULT
    ANOMALY_BOOTSTRAP_SAMPLES: int = constants.ANOMALY_BOOTSTRAP_SAMPLES_DEFAULT
    ANOMALY_SCORE_THRESHOLD_HIGH: float = constants.ANOMALY_SCORE_THRESHOLD_HIGH_DEFAULT
    ANOMALY_SCORE_THRESHOLD_MEDIUM: float = constants.ANOMALY_SCORE_THRESHOLD_MEDIUM_DEFAULT
    ANOMALY_STALE_DATA_MINUTES: int = constants.ANOMALY_STALE_DATA_MINUTES_DEFAULT

    # Phase 4 — Forecast plugin
    FORECAST_ENABLED: bool = True
    FORECAST_STORAGE_DIR: Path = constants.FORECAST_STORAGE_DIR_DEFAULT
    FORECAST_RETENTION_HOURS: int = constants.FORECAST_RETENTION_HOURS_DEFAULT
    FORECAST_DEFAULT_HORIZON_MINUTES: int = constants.FORECAST_DEFAULT_HORIZON_MINUTES_DEFAULT
    FORECAST_DEFAULT_SAMPLING_INTERVAL_MINUTES: int = constants.FORECAST_DEFAULT_SAMPLING_INTERVAL_MINUTES_DEFAULT

    # AQI Module
    AQI_STORAGE_FILE: Path = Path('./data/aqi_latest.json')
    AQI_STANDARD: str = constants.DEFAULT_AQI_STANDARD

    model_config = SettingsConfigDict(
        env_prefix='NAVOS_',
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

@lru_cache()
def get_settings() -> Settings:
    return Settings()
