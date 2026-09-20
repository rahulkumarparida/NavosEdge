from typing import List, Optional
from pydantic import BaseModel
from app.schemas.anomaly import AnomalyReport
from app.schemas.source_classification import SourceClassificationResult

class SensorHealth(BaseModel):
    status: str  # "ok", "degraded", "stale", "invalid"
    issues: List[str]

class AnomalyResult(BaseModel):
    is_anomalous: bool
    deviations: List[str]

class ForecastResult(BaseModel):
    pm2_5_persistence: Optional[float] = None
    pm10_persistence: Optional[float] = None

class AdvisoryResult(BaseModel):
    level: str  # "NORMAL", "CAUTION", "WARNING", "MAINTENANCE"
    messages: List[str]

class PipelineResults(BaseModel):
    health: SensorHealth
    anomaly: AnomalyResult
    forecast: ForecastResult
    advisory: AdvisoryResult
    anomaly_report: Optional[AnomalyReport] = None
    source_classification: Optional[SourceClassificationResult] = None
