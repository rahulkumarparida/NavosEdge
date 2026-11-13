from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core import constants

DEFAULT_ACK_SIGNING_SECRET = "navosedge-local-dev-ack-secret-change-in-prod"


class Settings(BaseSettings):
    ENV: Literal["development", "production"] = "development"
    CORS_ORIGINS: str = "*"
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
    ADVISORY_LANGUAGE: str = "en"

    # Emergency Data Layer (Phase 1)
    EMERGENCY_DB_PATH: Path = Path("data/navos_emergency.db")

    # Phase 2 — Hazard Classification & Response Policy Thresholds
    # Derived from existing AdvisoryConfig (app/advisory/rules.py),
    # ModularPipeline (app/services/pipeline.py: uncertainty > 0.60),
    # and SourceClassifier (app/source_classifier/classifier.py: stale > 300s).
    HAZARD_AQI_STANDARD: str = constants.DEFAULT_AQI_STANDARD
    HAZARD_UNCERTAINTY_THRESHOLD: float = 0.60
    HAZARD_MIN_CLASS_CONFIDENCE: float = 0.65
    HAZARD_STALE_DATA_SECONDS: float = 300.0
    HAZARD_SUDDEN_PM25_DELTA_UGM3: float = 35.0
    HAZARD_SUDDEN_PM10_DELTA_UGM3: float = 75.0
    HAZARD_SUDDEN_MQ_DELTA_V: float = 0.80
    HAZARD_PERSISTENT_MIN_READINGS: int = 3
    HAZARD_RECOVERY_MIN_READINGS: int = 2

    # Phase 3 — ESP32 Wireless Actuator Integration
    ACTUATOR_HTTP_PORT: int = 8080
    ACTUATOR_COMMAND_TIMEOUT_S: float = 5.0
    ACTUATOR_HEARTBEAT_STALE_S: float = 90.0
    ACTUATOR_DUPLICATE_WINDOW_S: float = 30.0
    ACTUATOR_DEFAULT_LEASE_S: int = 60
    ACTUATOR_DEMO_MODE: bool = False

    # Phase 4 — Twilio Emergency Notification & Caregiver Escalation
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_FROM_NUMBER: Optional[str] = None
    TWILIO_MODE: Literal["SIMULATED", "LIVE"] = "SIMULATED"
    PUBLIC_WEBHOOK_BASE_URL: Optional[str] = None
    ACK_SIGNING_SECRET: str = DEFAULT_ACK_SIGNING_SECRET
    TWILIO_TIMEOUT_S: float = 10.0
    ESCALATION_ACK_TIMEOUT_S: float = 120.0
    ESCALATION_DEMO_TIMEOUT_S: float = 30.0
    ESCALATION_DEMO_MODE: bool = False
    TWILIO_TRIAL_MODE: bool = True
    TWILIO_VERIFIED_NUMBERS: Optional[str] = None
    TWILIO_TEST_RECIPIENT: Optional[str] = None
    TWILIO_SECONDARY_RECIPIENT: Optional[str] = None
    TWILIO_MAX_RETRIES: int = 2
    TWILIO_RETRY_BACKOFF_S: float = 0.25
    TWILIO_DISPATCH_MODE: Literal["REST", "STUDIO"] = "REST"
    TWILIO_STUDIO_FLOW_SID: Optional[str] = None
    TWILIO_VALIDATE_WEBHOOK_SIGNATURE: bool = True

    @property
    def twilio_verified_numbers_list(self) -> list[str]:
        """Return configured E.164 verified numbers for Twilio Trial allowlist checks."""
        if not self.TWILIO_VERIFIED_NUMBERS:
            return []
        return [
            item.strip()
            for item in str(self.TWILIO_VERIFIED_NUMBERS).split(",")
            if item.strip()
        ]

    # Phase 5 — Manager & Operator Authorization
    MANAGER_API_KEY: Optional[str] = None

    model_config = SettingsConfigDict(
        env_prefix='NAVOS_',
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore'
    )

def parse_cors_origins(raw: str) -> list[str]:
    """Parse comma-separated CORS origins from NAVOS_CORS_ORIGINS."""
    origins = [item.strip() for item in (raw or "*").split(",") if item.strip()]
    return origins or ["*"]


def validate_production_config(settings: Settings) -> None:
    """
    Fail closed on unsafe configuration when NAVOS_ENV=production.
    Never includes secret values in exception messages.
    """
    if settings.ENV != "production":
        return

    errors: list[str] = []
    if not settings.MANAGER_API_KEY or not settings.MANAGER_API_KEY.strip():
        errors.append("NAVOS_MANAGER_API_KEY must be set in production mode.")
    if (
        not settings.ACK_SIGNING_SECRET
        or settings.ACK_SIGNING_SECRET == DEFAULT_ACK_SIGNING_SECRET
        or len(settings.ACK_SIGNING_SECRET.strip()) < 16
    ):
        errors.append(
            "NAVOS_ACK_SIGNING_SECRET must be changed from the default and be at least 16 characters."
        )

    if settings.TWILIO_MODE == "LIVE":
        missing_twilio = [
            name
            for name, val in (
                ("NAVOS_TWILIO_ACCOUNT_SID", settings.TWILIO_ACCOUNT_SID),
                ("NAVOS_TWILIO_AUTH_TOKEN", settings.TWILIO_AUTH_TOKEN),
                ("NAVOS_TWILIO_FROM_NUMBER", settings.TWILIO_FROM_NUMBER),
                ("NAVOS_PUBLIC_WEBHOOK_BASE_URL", settings.PUBLIC_WEBHOOK_BASE_URL),
            )
            if not val or not str(val).strip()
        ]
        if missing_twilio:
            errors.append(
                "NAVOS_TWILIO_MODE=LIVE requires: " + ", ".join(missing_twilio) + "."
            )
        elif not str(settings.PUBLIC_WEBHOOK_BASE_URL).strip().startswith(("https://", "http://")):
            errors.append(
                "NAVOS_PUBLIC_WEBHOOK_BASE_URL must start with https:// (or http:// for local tunnel)."
            )
        if settings.TWILIO_DISPATCH_MODE == "STUDIO" and (
            not settings.TWILIO_STUDIO_FLOW_SID or not str(settings.TWILIO_STUDIO_FLOW_SID).strip()
        ):
            errors.append(
                "NAVOS_TWILIO_DISPATCH_MODE=STUDIO requires NAVOS_TWILIO_STUDIO_FLOW_SID."
            )

    if errors:
        raise RuntimeError("Production configuration validation failed: " + " ".join(errors))


@lru_cache()
def get_settings() -> Settings:
    return Settings()
