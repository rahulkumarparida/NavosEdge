"""
Pydantic schemas for the anomaly detection subsystem output.

These models define the structured JSON output returned alongside the
existing pipeline results.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel


class AnomalySeverity(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AnomalyConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class AnomalySystemState(str, Enum):
    BOOTSTRAPPING = "BOOTSTRAPPING"
    CALIBRATING = "CALIBRATING"
    LEARNING = "LEARNING"
    MONITORING = "MONITORING"
    DEGRADED = "DEGRADED"


class FeatureEvidence(BaseModel):
    actual: Optional[float] = None
    expected: Optional[float] = None
    residual: Optional[float] = None
    score: float = 0.0
    status: str = "UNAVAILABLE"
    sensor_health: str = "UNKNOWN"


class AnomalyDecision(BaseModel):
    detected: bool = False
    score: float = 0.0
    severity: AnomalySeverity = AnomalySeverity.NONE


class DataQuality(BaseModel):
    status: str = "OK"
    missing_features: List[str] = []
    features_used: List[str] = []
    sensor_health: str = "UNKNOWN"
    confidence: AnomalyConfidence = AnomalyConfidence.INSUFFICIENT_DATA


class AnomalyReport(BaseModel):
    """Full structured anomaly report for a single observation."""

    timestamp: Optional[datetime] = None
    anomaly: AnomalyDecision = AnomalyDecision()
    sensor_evidence: Dict[str, FeatureEvidence] = {}
    data_quality: DataQuality = DataQuality()
    system_state: AnomalySystemState = AnomalySystemState.BOOTSTRAPPING
    anomaly_source: str = "UNKNOWN"
    anomaly_source_detail: str = ""
    explanations: List[str] = []

    @classmethod
    def from_engine_dict(cls, data: dict) -> "AnomalyReport":
        """Construct from the dict returned by AnomalyEngine.analyse()."""
        anomaly_data = data.get("anomaly", {})
        dq_data = data.get("data_quality", {})

        evidence = {}
        for fname, fdata in data.get("sensor_evidence", {}).items():
            evidence[fname] = FeatureEvidence(**fdata)

        return cls(
            timestamp=data.get("timestamp"),
            anomaly=AnomalyDecision(
                detected=anomaly_data.get("detected", False),
                score=anomaly_data.get("score", 0.0),
                severity=anomaly_data.get("severity", "NONE"),
            ),
            sensor_evidence=evidence,
            data_quality=DataQuality(
                status=dq_data.get("status", "UNKNOWN"),
                missing_features=dq_data.get("missing_features", []),
                features_used=dq_data.get("features_used", []),
                sensor_health=dq_data.get("sensor_health", "UNKNOWN"),
                confidence=dq_data.get("confidence", "INSUFFICIENT_DATA"),
            ),
            system_state=data.get("system_state", "BOOTSTRAPPING"),
            anomaly_source=data.get("anomaly_source", "UNKNOWN"),
            anomaly_source_detail=data.get("anomaly_source_detail", ""),
            explanations=data.get("explanations", []),
        )
