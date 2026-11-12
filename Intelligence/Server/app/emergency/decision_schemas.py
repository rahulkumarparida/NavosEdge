"""
Typed Pydantic v2 decision schemas for Phase 2: Environmental Hazard
Classification and Response Policy Engine.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.emergency.schemas import ensure_utc, utc_now


class HazardSeverity(str, Enum):
    """Consistent 4-tier severity classification required by Phase 2."""

    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


SEVERITY_RANK: Dict[HazardSeverity, int] = {
    HazardSeverity.NORMAL: 0,
    HazardSeverity.WARNING: 1,
    HazardSeverity.CRITICAL: 2,
    HazardSeverity.EMERGENCY: 3,
}


class HazardType(str, Enum):
    """Environmental hazard categories evaluated from pipeline telemetry."""

    NONE = "NONE"
    PARTICULATE_ELEVATED = "PARTICULATE_ELEVATED"
    PARTICULATE_SUDDEN_INCREASE = "PARTICULATE_SUDDEN_INCREASE"
    PARTICULATE_PERSISTENT = "PARTICULATE_PERSISTENT"
    PARTICULATE_CRITICAL = "PARTICULATE_CRITICAL"
    GAS_ELEVATED = "GAS_ELEVATED"
    GAS_HAZARD = "GAS_HAZARD"
    COMBINED_GAS_AND_PARTICULATE = "COMBINED_GAS_AND_PARTICULATE"
    CONFLICTING_READINGS = "CONFLICTING_READINGS"
    UNCERTAIN_PREDICTION = "UNCERTAIN_PREDICTION"
    SENSOR_ANOMALY_OR_FAULT = "SENSOR_ANOMALY_OR_FAULT"
    MISSING_OR_STALE_DATA = "MISSING_OR_STALE_DATA"
    ENVIRONMENTAL_RECOVERY = "ENVIRONMENTAL_RECOVERY"


class EnvironmentalTrend(str, Enum):
    """Environmental trajectory derived from EMA, OLS, MAD, and rolling history."""

    NORMAL_FLUCTUATION = "NORMAL_FLUCTUATION"
    GRADUAL_DETERIORATION = "GRADUAL_DETERIORATION"
    SUDDEN_ANOMALY = "SUDDEN_ANOMALY"
    PERSISTENT_HAZARD = "PERSISTENT_HAZARD"
    RECOVERY_TREND = "RECOVERY_TREND"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ResponseCategory(str, Enum):
    """Standardized response policy recommendations (distinct from execution)."""

    CONTINUE_MONITORING = "CONTINUE_MONITORING"
    LOCAL_WARNING = "LOCAL_WARNING"
    ACTIVATE_FILTRATION = "ACTIVATE_FILTRATION"
    RESTRICT_OUTDOOR_AIR_INTAKE = "RESTRICT_OUTDOOR_AIR_INTAKE"
    REQUEST_HUMAN_INTERVENTION = "REQUEST_HUMAN_INTERVENTION"
    EMERGENCY_NOTIFICATION = "EMERGENCY_NOTIFICATION"


class ActionExecutionState(str, Enum):
    """
    Explicitly distinguishes recommended policy actions from executed and
    acknowledged physical actions (Safety Rule 9).
    """

    RECOMMENDED = "RECOMMENDED"
    EXECUTED = "EXECUTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    UNAVAILABLE = "UNAVAILABLE"
    INHIBITED_BY_SAFETY_RULE = "INHIBITED_BY_SAFETY_RULE"


class EventLifecycleTransition(str, Enum):
    """Lifecycle transitions for deduplicated emergency event management."""

    NONE = "NONE"
    NEW_HAZARD_DETECTED = "NEW_HAZARD_DETECTED"
    EXISTING_HAZARD_CONTINUED = "EXISTING_HAZARD_CONTINUED"
    SEVERITY_ESCALATED = "SEVERITY_ESCALATED"
    SEVERITY_REDUCED = "SEVERITY_REDUCED"
    HAZARD_RECOVERING = "HAZARD_RECOVERING"
    EVENT_RESOLVED = "EVENT_RESOLVED"


class ActuatorPolicyRecommendation(BaseModel):
    """
    Structured appliance-policy recommendation that enforces Safety Rule 1:
    never recommend an unfiltered fan as a particulate filtration device.
    """

    model_config = ConfigDict(from_attributes=True)

    actuator_id: Optional[str] = None
    actuator_type: Optional[str] = None
    is_filtration_capable: bool = False
    is_available: bool = False
    recommended_action: str = Field(
        default="NONE",
        description=(
            "NONE | ACTIVATE_FILTRATION | DO_NOT_ACTIVATE_UNFILTERED_FAN | "
            "DO_NOT_ACTIVATE_ON_GAS_HAZARD | INHIBITED_UNCERTAIN_OR_CONFLICT | "
            "ACTUATOR_UNAVAILABLE"
        ),
    )
    execution_state: ActionExecutionState = ActionExecutionState.RECOMMENDED
    rationale: str = ""


class HazardEvaluationResult(BaseModel):
    """
    Stage 1 Output: What is happening in the environment based on verified
    sensor measurements, anomaly models (EMA/OLS/MAD), and GasNet inference.
    """

    model_config = ConfigDict(from_attributes=True)

    node_id: str
    detection_timestamp: datetime = Field(default_factory=utc_now)
    hazard_type: HazardType = HazardType.NONE
    severity: HazardSeverity = HazardSeverity.NORMAL
    environmental_trend: EnvironmentalTrend = EnvironmentalTrend.NORMAL_FLUCTUATION
    relevant_measurements: Dict[str, Optional[float]] = Field(default_factory=dict)
    supporting_evidence: List[str] = Field(default_factory=list)
    gas_identity_candidate: Optional[str] = Field(
        default=None,
        description=(
            "Candidate gas class from TinyGasNet if confidence/uncertainty gates pass; "
            "explicitly 'UNESTABLISHED' when MOS cross-sensitivity or uncertainty prevents "
            "specific gas identification."
        ),
    )
    pollution_source_candidate: Optional[str] = None
    model_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    model_uncertainty: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    is_uncertain: bool = False
    has_sensor_conflict: bool = False
    has_missing_data: bool = False
    is_stale_data: bool = False
    has_hardware_fault: bool = False
    consecutive_hazard_count: int = 0
    consecutive_recovery_count: int = 0
    reason: str

    @field_validator("detection_timestamp")
    @classmethod
    def _normalize_dt(cls, v: datetime) -> datetime:
        res = ensure_utc(v)
        assert res is not None
        return res


class PolicyDecisionResult(BaseModel):
    """
    Stage 2 Output: What should happen in response to the evaluated hazard,
    including safety-gated response categories, actuator recommendations,
    human intervention flags, and deduplicated event lifecycle state.
    """

    model_config = ConfigDict(from_attributes=True)

    node_id: str
    decision_timestamp: datetime = Field(default_factory=utc_now)
    hazard_type: HazardType
    severity: HazardSeverity
    environmental_trend: EnvironmentalTrend
    relevant_measurements: Dict[str, Optional[float]] = Field(default_factory=dict)
    supporting_evidence: List[str] = Field(default_factory=list)
    model_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    model_uncertainty: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    reason: str
    recommended_responses: List[ResponseCategory] = Field(default_factory=list)
    action_states: Dict[str, ActionExecutionState] = Field(default_factory=dict)
    human_intervention_recommended: bool = False
    actuator_recommendation: ActuatorPolicyRecommendation = Field(
        default_factory=ActuatorPolicyRecommendation
    )
    local_warning_preserved: bool = True
    lifecycle_transition: EventLifecycleTransition = EventLifecycleTransition.NONE
    active_event_id: Optional[str] = None
    evaluation: HazardEvaluationResult

    @field_validator("decision_timestamp")
    @classmethod
    def _normalize_dt(cls, v: datetime) -> datetime:
        res = ensure_utc(v)
        assert res is not None
        return res

