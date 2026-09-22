"""
Pydantic schemas for Phase 4 — Lightweight Autoregressive Forecast Plugin.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class TrendDirection(str, Enum):
    RISING = "rising"
    FALLING = "falling"
    STABLE = "stable"
    UNKNOWN = "unknown"


class ForecastReliability(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNAVAILABLE = "unavailable"


class ForecastStatus(str, Enum):
    OK = "ok"
    INSUFFICIENT_DATA = "insufficient_data"
    NO_VALID_CHANNELS = "no_valid_channels"
    ERROR = "error"


# --- Ingest ---

class ForecastReadingInput(BaseModel):
    """Minimal reading submitted to the forecast plugin."""
    node_id: str = Field(min_length=1, max_length=64, pattern=r'^[a-zA-Z0-9_-]+$')
    timestamp: datetime
    PM1_0: Optional[float] = Field(default=None, ge=0)
    PM2_5: Optional[float] = Field(default=None, ge=0)
    PM10: Optional[float] = Field(default=None, ge=0)
    is_synthetic: bool = False


class ForecastReadingAccepted(BaseModel):
    node_id: str
    timestamp: datetime
    stored: bool
    message: str = "Reading accepted"


# --- Single-channel prediction ---

class ChannelPrediction(BaseModel):
    channel: str
    predicted_values: List[float]
    predicted_timestamps: List[datetime]
    trend: TrendDirection
    persistence_baseline: Optional[List[float]] = None
    mae_vs_persistence: Optional[float] = None


# --- Forecast response ---

class ForecastResponse(BaseModel):
    node_id: str
    status: ForecastStatus
    reliability: ForecastReliability
    generated_at: datetime
    horizon_minutes: int
    sampling_interval_minutes: int
    history_points_used: int
    channels: List[ChannelPrediction] = []
    message: str = ""
    experimental_warning: str = (
        "Forecasts are experimental and have not been validated "
        "against real sensor data. Use for informational purposes only."
    )


# --- History / status ---

class ForecastHistoryResponse(BaseModel):
    node_id: str
    total_records: int
    oldest_timestamp: Optional[datetime] = None
    newest_timestamp: Optional[datetime] = None
    retention_hours: int
    storage_path: str
    channels_available: List[str] = []


# --- Cleanup ---

class CleanupResponse(BaseModel):
    node_id: Optional[str] = None
    records_deleted: int
    message: str


# --- Synthetic generator ---

class SyntheticGeneratorConfig(BaseModel):
    node_id: str = Field(default="synthetic-node-01")
    duration_hours: int = Field(default=48, ge=1, le=168)
    sampling_interval_minutes: int = Field(default=5, ge=1, le=60)
    seed: Optional[int] = None
    include_spikes: bool = True
    include_trend: bool = True
    noise_level: float = Field(default=1.0, ge=0.0, le=10.0)


class SyntheticGeneratorResponse(BaseModel):
    node_id: str
    records_generated: int
    duration_hours: int
    sampling_interval_minutes: int
    seed_used: int
    message: str
