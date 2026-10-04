"""
Manager Data Schemas and Pydantic Models
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from datetime import datetime, timezone


class SourcePredictionInput(BaseModel):
    value: Any = "unknown"
    confidence: Optional[float] = None


class ForecastPredictionInput(BaseModel):
    value: Any = None
    confidence: Optional[float] = None


class PredictionsInput(BaseModel):
    source: Optional[SourcePredictionInput] = Field(default_factory=SourcePredictionInput)
    forecast: Optional[ForecastPredictionInput] = Field(default_factory=ForecastPredictionInput)


class NodeTelemetryPayload(BaseModel):
    node_id: Optional[str] = None
    location: Optional[str] = None
    aqi: Optional[Union[float, str]] = None
    pm: Optional[Union[Dict[str, Any], Any]] = Field(default_factory=dict)
    temperature_C: Optional[Union[float, str]] = None
    humidity_pct: Optional[Union[float, str]] = None
    predictions: Optional[Dict[str, Any]] = Field(default_factory=dict)
    advisory: Optional[Dict[str, Any]] = Field(default_factory=dict)
    timestamp: Optional[str] = None


class NodeRegistrationPayload(BaseModel):
    node_id: str
    location: Optional[str] = None


class NodeState(BaseModel):
    node_id: str
    location: str
    status: str = "active"  # "active" or "inactive"
    last_seen: str
    last_updated_seconds_ago: float = 0.0
    aqi: Optional[float] = None
    pm: Dict[str, float] = Field(default_factory=dict)
    temperature_C: float = 0.0
    humidity_pct: float = 0.0
    source_prediction: str = "unknown"
    source_confidence: Optional[float] = None
    predictions: Dict[str, Any] = Field(default_factory=dict)
    advisory: Dict[str, Any] = Field(default_factory=dict)


class OverallData(BaseModel):
    aqi: Optional[float] = None
    PM1_0: float = 0.0
    PM2_5: float = 0.0
    PM10: float = 0.0
    temperature_C: float = 0.0
    humidity_pct: float = 0.0


class OverviewResponse(BaseModel):
    active_nodes: int = 0
    inactive_nodes: int = 0
    total_nodes: int = 0
    overall: OverallData = Field(default_factory=OverallData)
    nodes: List[NodeState] = Field(default_factory=list)


class SystemHealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "1.0.0"
    timestamp: str
    active_nodes: int
    inactive_nodes: int
    total_nodes: int
