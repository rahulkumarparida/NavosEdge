from enum import Enum
from pydantic import BaseModel
from typing import Optional, Dict

class InferenceStatus(str, Enum):
    SUCCESS = 'success'
    NOT_CONFIGURED = 'not_configured'
    ERROR = 'error'

class InferenceResult(BaseModel):
    status: InferenceStatus
    gas_class: Optional[str] = None
    class_confidence: Optional[float] = None
    class_probabilities: Optional[Dict[str, float]] = None
    safety_status: Optional[str] = None
    safety_confidence: Optional[float] = None
    uncertainty: Optional[float] = None
    error_message: Optional[str] = None
    inference_time_ms: Optional[float] = None

    @classmethod
    def not_configured(cls) -> 'InferenceResult':
        return cls(status=InferenceStatus.NOT_CONFIGURED)

    @classmethod
    def from_error(cls, message: str) -> 'InferenceResult':
        return cls(status=InferenceStatus.ERROR, error_message=message)
