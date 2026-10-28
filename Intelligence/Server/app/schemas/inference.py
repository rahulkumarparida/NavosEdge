from enum import Enum
from pydantic import BaseModel
from typing import Optional, Dict

class InferenceStatus(str, Enum):
    SUCCESS = 'success'
    NOT_CONFIGURED = 'not_configured'
    ERROR = 'error'
    SENSOR_FAULT = 'sensor_fault'
    ABSTAIN = 'abstain'

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

    @classmethod
    def from_sensor_fault(
        cls, message: str, uncertainty: float = 1.0, inference_time_ms: float = 0.0
    ) -> 'InferenceResult':
        return cls(
            status=InferenceStatus.SENSOR_FAULT,
            gas_class="SENSOR_FAULT",
            class_confidence=0.0,
            class_probabilities=None,
            safety_status="unknown",
            safety_confidence=0.0,
            uncertainty=uncertainty,
            error_message=message,
            inference_time_ms=inference_time_ms,
        )

    @classmethod
    def from_abstain(
        cls, message: str, uncertainty: float = 1.0, inference_time_ms: float = 0.0
    ) -> 'InferenceResult':
        return cls(
            status=InferenceStatus.ABSTAIN,
            gas_class="ABSTAIN",
            class_confidence=0.0,
            class_probabilities=None,
            safety_status="unknown",
            safety_confidence=0.0,
            uncertainty=uncertainty,
            error_message=message,
            inference_time_ms=inference_time_ms,
        )

