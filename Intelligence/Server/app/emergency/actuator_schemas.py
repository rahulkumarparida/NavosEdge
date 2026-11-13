"""
Validated Pydantic v2 command, acknowledgement, and heartbeat contracts for
Phase 3: ESP32 Wireless Actuator Integration.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.emergency.schemas import (
    ActuatorCommandResponse,
    ActuatorResponse,
    ensure_utc,
    utc_now,
    validate_identifier,
)


class ActuatorCommandType(str, Enum):
    """Supported wireless commands between UNO Q and NodeMCU ESP-32S V1.1."""

    FAN_ON = "FAN_ON"
    FAN_OFF = "FAN_OFF"
    LIGHT_ON = "LIGHT_ON"
    LIGHT_OFF = "LIGHT_OFF"
    GET_STATUS = "GET_STATUS"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class ActuatorControlMode(str, Enum):
    """
    Distinguishes real environmental protection mode from explicit
    demonstration or manual operator control.
    """

    PROTECTION_MODE = "PROTECTION_MODE"
    DEMO_MODE = "DEMO_MODE"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


class ActuatorPhysicalOutputState(str, Enum):
    """
    Physical output state reported by the ESP32 actuator firmware.
    `SAFE_LOCKED_OFF` indicates the firmware received and validated the command
    while keeping GPIO18 hardware-locked LOW because `PHYSICAL_DRIVER_VERIFIED`
    is false.
    """

    ON = "ON"
    OFF = "OFF"
    SAFE_LOCKED_OFF = "SAFE_LOCKED_OFF"
    FAILSAFE_OFF = "FAILSAFE_OFF"
    UNKNOWN = "UNKNOWN"


class ActuatorAckStatus(str, Enum):
    """
    Separates command receipt/validation (`ACKNOWLEDGED`) from actual output
    execution (`EXECUTED`) and error states (`REJECTED`, `ERROR`).
    """

    ACKNOWLEDGED = "ACKNOWLEDGED"
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"


class ActuatorCommandPayload(BaseModel):
    """Validated JSON command sent from UNO Q Intelligence Server to ESP32."""

    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(
        default_factory=lambda: f"cmd-{uuid.uuid4().hex[:12]}",
        min_length=1,
        max_length=64,
    )
    node_id: str = Field(..., min_length=1, max_length=64)
    actuator_id: str = Field(..., min_length=1, max_length=64)
    command: ActuatorCommandType
    event_id: Optional[str] = Field(default=None, max_length=64)
    control_mode: ActuatorControlMode = Field(
        default=ActuatorControlMode.PROTECTION_MODE
    )
    lease_seconds: Optional[int] = Field(default=60, ge=5, le=3600)
    timestamp: datetime = Field(default_factory=utc_now)

    @field_validator("command_id", "node_id", "actuator_id")
    @classmethod
    def _validate_ids(cls, v: str) -> str:
        return validate_identifier(v, "identifier")

    @field_validator("event_id")
    @classmethod
    def _validate_event_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return validate_identifier(v, "event_id")

    @field_validator("timestamp")
    @classmethod
    def _normalize_ts(cls, v: datetime) -> datetime:
        normalized = ensure_utc(v)
        assert normalized is not None
        return normalized


class ActuatorCommandAck(BaseModel):
    """Validated JSON acknowledgement returned by ESP32 to UNO Q."""

    model_config = ConfigDict(extra="ignore")

    command_id: str = Field(..., min_length=1, max_length=64)
    actuator_id: str = Field(..., min_length=1, max_length=64)
    status: ActuatorAckStatus
    output_state: ActuatorPhysicalOutputState
    physical_driver_verified: bool = False
    timestamp: datetime = Field(default_factory=utc_now)
    error_details: Optional[str] = Field(default=None, max_length=500)

    @field_validator("command_id", "actuator_id")
    @classmethod
    def _validate_ids(cls, v: str) -> str:
        return validate_identifier(v, "identifier")

    @field_validator("timestamp")
    @classmethod
    def _normalize_ts(cls, v: datetime) -> datetime:
        normalized = ensure_utc(v)
        assert normalized is not None
        return normalized


class ActuatorDispatchRequest(BaseModel):
    """API request payload for dispatching a command to an actuator."""

    model_config = ConfigDict(extra="forbid")

    command: ActuatorCommandType
    control_mode: ActuatorControlMode = Field(default=ActuatorControlMode.DEMO_MODE)
    event_id: Optional[str] = Field(default=None, max_length=64)
    lease_seconds: int = Field(default=60, ge=5, le=3600)
    reason: Optional[str] = Field(default=None, max_length=300)

    @field_validator("event_id")
    @classmethod
    def _validate_event_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return validate_identifier(v, "event_id")


class ActuatorHeartbeatRequest(BaseModel):
    """Registration & heartbeat payload sent by ESP32 to UNO Q."""

    model_config = ConfigDict(extra="ignore")

    actuator_id: str = Field(..., min_length=1, max_length=64)
    associated_node_id: str = Field(..., min_length=1, max_length=64)
    actuator_type: str = Field(
        default="ESP32_FAN_5V_UNFILTERED", min_length=1, max_length=64
    )
    device_name: str = Field(
        default="NodeMCU ESP-32S V1.1 Fan Actuator", min_length=1, max_length=120
    )
    ip_address: Optional[str] = Field(default=None, max_length=64)
    output_state: ActuatorPhysicalOutputState = Field(
        default=ActuatorPhysicalOutputState.OFF
    )
    physical_driver_verified: bool = False
    gpio_pin: int = Field(default=25, ge=0, le=39)
    firmware_version: Optional[str] = Field(default=None, max_length=64)
    timestamp: datetime = Field(default_factory=utc_now)

    @field_validator("actuator_id", "associated_node_id")
    @classmethod
    def _validate_ids(cls, v: str) -> str:
        return validate_identifier(v, "identifier")

    @field_validator("timestamp")
    @classmethod
    def _normalize_ts(cls, v: datetime) -> datetime:
        normalized = ensure_utc(v)
        assert normalized is not None
        return normalized


class ActuatorHeartbeatResponse(ActuatorResponse):
    """Heartbeat response returning registration info plus authoritative alert light state."""

    system_ready: bool = True
    desired_state: ActuatorPhysicalOutputState = ActuatorPhysicalOutputState.OFF
    active_event_id: Optional[str] = None
    active_event_count: int = 0
    severity: Optional[str] = None
    alert_type: Optional[str] = None


class ActuatorDispatchResult(BaseModel):
    """Structured result returned by `ActuatorService` after dispatch or suppression."""

    model_config = ConfigDict(from_attributes=True)

    dispatched: bool
    suppressed: bool = False
    suppression_reason: Optional[str] = None
    control_mode: ActuatorControlMode
    command_log: Optional[ActuatorCommandResponse] = None
    acknowledgement: Optional[ActuatorCommandAck] = None
    actuator: Optional[ActuatorResponse] = None

