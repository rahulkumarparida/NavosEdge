"""Minimal public intelligence response contract."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.advisory.schemas import AdvisoryResult


class PredictionOutput(BaseModel):
    """Only the public prediction value and confidence."""

    value: Any = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class IntelligencePredictions(BaseModel):
    source: PredictionOutput
    forecast: PredictionOutput


class IntelligenceResult(BaseModel):
    """Compact user-facing result; internal diagnostics stay server-side."""

    aqi: Optional[float] = None
    pm: Dict[str, float]
    temperature_C: float
    humidity_pct: float
    predictions: IntelligencePredictions
    advisory: AdvisoryResult


class ForecastValue(BaseModel):
    PM1_0: List[float] = Field(default_factory=list)
    PM2_5: List[float] = Field(default_factory=list)
    PM10: List[float] = Field(default_factory=list)
    status: str
