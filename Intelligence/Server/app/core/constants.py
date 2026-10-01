"""
constants.py — Centralized constants for Intelligence Server module.
Single source of truth for default server settings, breakpoints, feature definitions, and model parameters.
"""

from pathlib import Path
from typing import Dict, List, Tuple

# ------------------------------------------------------------------
# Server & Application Defaults
# ------------------------------------------------------------------
APP_NAME_DEFAULT: str = "NavosEdge Intelligence Server"
APP_VERSION_DEFAULT: str = "0.1.0"
HOST_DEFAULT: str = "0.0.0.0"
PORT_DEFAULT: int = 8420
LOG_LEVEL_DEFAULT: str = "INFO"

# Directory Defaults
DATA_DIR_DEFAULT: Path = Path("./data")
ARTIFACTS_DIR_DEFAULT: Path = Path("./artifacts")
MODELS_DIR_DEFAULT: Path = Path("./models")

# Network & Payload Limits
MAX_PAYLOAD_BYTES_DEFAULT: int = 65536
SSE_HEARTBEAT_INTERVAL_S_DEFAULT: float = 15.0
STORAGE_MAX_FILE_SIZE_MB_DEFAULT: float = 50.0
STORAGE_MAX_FILES_PER_NODE_DEFAULT: int = 30

# Model Weight Files
MODEL_WEIGHTS_FILE_DEFAULT: str = "gasnet_weights.npz"
MODEL_PREPROCESS_FILE_DEFAULT: str = "model_metadata.json"

# ------------------------------------------------------------------
# Anomaly Detection Engine Defaults
# ------------------------------------------------------------------
ANOMALY_HISTORY_WINDOW_HOURS_DEFAULT: int = 24
ANOMALY_MODEL_UPDATE_INTERVAL_MINUTES_DEFAULT: int = 15
ANOMALY_MIN_SAMPLES_FOR_REGRESSION_DEFAULT: int = 30
ANOMALY_MIN_SAMPLES_FOR_MONITORING_DEFAULT: int = 10
ANOMALY_BOOTSTRAP_SAMPLES_DEFAULT: int = 5
ANOMALY_SCORE_THRESHOLD_HIGH_DEFAULT: float = 3.0
ANOMALY_SCORE_THRESHOLD_MEDIUM_DEFAULT: float = 2.0
ANOMALY_STALE_DATA_MINUTES_DEFAULT: int = 30

# ------------------------------------------------------------------
# Forecast Plugin Defaults
# ------------------------------------------------------------------
FORECAST_STORAGE_DIR_DEFAULT: Path = Path("./data/forecast")
FORECAST_RETENTION_HOURS_DEFAULT: int = 48
FORECAST_MAX_FILE_SIZE_MB_DEFAULT: float = 10.0
FORECAST_DEFAULT_HORIZON_MINUTES_DEFAULT: int = 60
FORECAST_DEFAULT_SAMPLING_INTERVAL_MINUTES_DEFAULT: int = 5
FORECAST_MIN_HISTORY_POINTS_DEFAULT: int = 12
FORECAST_MAX_AR_ORDER_DEFAULT: int = 6
FORECAST_TREND_THRESHOLD_DEFAULT: float = 0.5
FORECAST_PM_CHANNELS: List[str] = ["PM1_0", "PM2_5", "PM10"]

# ------------------------------------------------------------------
# AQI Standard Breakpoint Tables
# Format: (c_low, c_high, i_low, i_high)
# ------------------------------------------------------------------
BREAKPOINTS_EPA: Dict[str, List[Tuple[float, float, float, float]]] = {
    "PM2_5": [
        (0.0, 12.0, 0.0, 50.0),
        (12.1, 35.4, 51.0, 100.0),
        (35.5, 55.4, 101.0, 150.0),
        (55.5, 150.4, 151.0, 200.0),
        (150.5, 250.4, 201.0, 300.0),
        (250.5, 350.4, 301.0, 400.0),
        (350.5, 500.4, 401.0, 500.0),
    ],
    "PM10": [
        (0.0, 54.0, 0.0, 50.0),
        (55.0, 154.0, 51.0, 100.0),
        (155.0, 254.0, 101.0, 150.0),
        (255.0, 354.0, 151.0, 200.0),
        (355.0, 424.0, 201.0, 300.0),
        (425.0, 504.0, 301.0, 400.0),
        (505.0, 604.0, 401.0, 500.0),
    ],
}
BREAKPOINTS_EPA["PM1_0"] = BREAKPOINTS_EPA["PM2_5"]

BREAKPOINTS_CPCB: Dict[str, List[Tuple[float, float, float, float]]] = {
    "PM2_5": [
        (0.0, 30.0, 0.0, 50.0),
        (30.1, 60.0, 51.0, 100.0),
        (60.1, 90.0, 101.0, 200.0),
        (90.1, 120.0, 201.0, 300.0),
        (120.1, 250.0, 301.0, 400.0),
        (250.1, 500.0, 401.0, 500.0),
    ],
    "PM10": [
        (0.0, 50.0, 0.0, 50.0),
        (50.1, 100.0, 51.0, 100.0),
        (100.1, 250.0, 101.0, 200.0),
        (251.0, 350.0, 201.0, 300.0),
        (351.0, 430.0, 301.0, 400.0),
        (430.1, 500.0, 401.0, 500.0),
    ],
}
BREAKPOINTS_CPCB["PM1_0"] = BREAKPOINTS_CPCB["PM2_5"]

DEFAULT_AQI_STANDARD: str = "EPA"

# ------------------------------------------------------------------
# Feature Definitions for ML & Source Classifier
# ------------------------------------------------------------------
RAW_FEATURES: List[str] = [
    "mq2_v",
    "mq9_v",
    "mq135_v",
    "temp_c",
    "hum_pct",
    "pm1_0",
    "pm2_5",
    "pm10",
]

DERIVED_FEATURES: List[str] = [
    "pm_coarse_ratio",
    "pm_fine_ratio",
    "mq_mean_v",
    "mq_max_v",
    "mq2_mq9_ratio",
    "mq135_mq2_ratio",
]

ALL_CLASSIFIER_FEATURES: List[str] = RAW_FEATURES + DERIVED_FEATURES
