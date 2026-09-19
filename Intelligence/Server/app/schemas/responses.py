from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from .inference import InferenceResult
from .pipeline import PipelineResults

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: datetime

class ReadinessResponse(BaseModel):
    ready: bool
    storage_ok: bool
    model_loaded: bool
    timestamp: datetime

class ReadingAccepted(BaseModel):
    node_id: str
    reading_id: str
    timestamp: datetime
    inference: InferenceResult
    pipeline: PipelineResults

class NodeInfo(BaseModel):
    node_id: str
    first_seen: datetime
    last_seen: datetime
    total_readings: int
    status: str = 'active'

class NodeStatusResponse(BaseModel):
    node_id: str
    status: str
    last_reading_at: Optional[datetime]
    total_readings: int
    inference_available: bool

class LatestReadingResponse(BaseModel):
    node_id: str
    reading: Dict[str, Any]
    inference: Optional[InferenceResult]
    recorded_at: datetime

class NodeListResponse(BaseModel):
    nodes: List[NodeInfo]
    count: int

class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    timestamp: datetime
