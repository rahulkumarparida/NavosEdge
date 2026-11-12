"""
Validated Pydantic v2 data contracts for the NavosEdge Emergency Response &
Smart Actuator data layer (Phase 1).
"""

from __future__ import annotations

import ipaddress
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Validation Patterns & Helpers
# ---------------------------------------------------------------------------

ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
# ITU-T E.164 format: '+' followed by country code (1-9) and subscriber digits (total 7-15 digits)
E164_PHONE_PATTERN = re.compile(r"^\+[1-9]\d{6,14}$")


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


def ensure_utc(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize any datetime to timezone-aware UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def validate_e164_phone(phone: str) -> str:
    """Validate and normalize an international E.164 phone number."""
    if not isinstance(phone, str):
        raise ValueError("Phone number must be a string")
    cleaned = phone.strip()
    if not E164_PHONE_PATTERN.match(cleaned):
        raise ValueError(
            f"Invalid E.164 phone number '{phone}'. Must start with '+' followed by "
            "7 to 15 digits with no spaces or symbols (e.g., +919876543210 or +14155552671)."
        )
    return cleaned


def validate_identifier(value: str, field_name: str = "id") -> str:
    """Validate safe alphanumeric/hyphen/underscore identifiers."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")
    cleaned = value.strip()
    if not ID_PATTERN.match(cleaned):
        raise ValueError(
            f"Invalid {field_name} '{value}'. Must be 1-64 characters matching [a-zA-Z0-9_-]."
        )
    return cleaned


# ---------------------------------------------------------------------------
# Domain Enumerations
# ---------------------------------------------------------------------------


class ConsentStatus(str, Enum):
    GRANTED = "GRANTED"
    PENDING = "PENDING"
    REVOKED = "REVOKED"


class NotificationChannel(str, Enum):
    SMS = "SMS"
    VOICE_CALL = "VOICE_CALL"


class NodeOperationalStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    MAINTENANCE = "MAINTENANCE"


class ActuatorConnectionStatus(str, Enum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"


class ActuatorState(str, Enum):
    ON = "ON"
    OFF = "OFF"
    FAILSAFE_OFF = "FAILSAFE_OFF"
    UNKNOWN = "UNKNOWN"


class EmergencySeverity(str, Enum):
    NORMAL = "NORMAL"
    LOW = "LOW"
    WARNING = "WARNING"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


class EmergencyEventStatus(str, Enum):
    DETECTED = "DETECTED"
    ACTIVE_UNACKNOWLEDGED = "ACTIVE_UNACKNOWLEDGED"
    ESCALATING = "ESCALATING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    RECOVERING = "RECOVERING"
    RESOLVED = "RESOLVED"
    CANCELLED = "CANCELLED"


class NotificationDeliveryStatus(str, Enum):
    QUEUED = "QUEUED"
    REQUESTED = "REQUESTED"
    ACCEPTED = "ACCEPTED"
    SENT = "SENT"
    RINGING = "RINGING"
    IN_PROGRESS = "IN_PROGRESS"
    DELIVERED = "DELIVERED"
    COMPLETED = "COMPLETED"
    UNDELIVERED = "UNDELIVERED"
    BUSY = "BUSY"
    NO_ANSWER = "NO_ANSWER"
    FAILED = "FAILED"


class HumanAcknowledgementStatus(str, Enum):
    PENDING = "PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    CHECKED_ON = "CHECKED_ON"
    EXPIRED = "EXPIRED"


class CommandExecutionStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"
    REJECTED = "REJECTED"


def _normalize_consent(val: Union[ConsentStatus, str, bool]) -> ConsentStatus:
    if isinstance(val, ConsentStatus):
        return val
    if isinstance(val, bool):
        return ConsentStatus.GRANTED if val else ConsentStatus.REVOKED
    if isinstance(val, str):
        upper = val.strip().upper()
        if upper in ("TRUE", "YES", "1", "GRANTED"):
            return ConsentStatus.GRANTED
        if upper in ("FALSE", "NO", "0", "REVOKED"):
            return ConsentStatus.REVOKED
        if upper == "PENDING":
            return ConsentStatus.PENDING
    raise ValueError(f"Invalid consent_status '{val}'. Expected GRANTED, PENDING, REVOKED, or bool.")


# ---------------------------------------------------------------------------
# 1. Resident Schemas
# ---------------------------------------------------------------------------


class ResidentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    resident_id: str = Field(
        default_factory=lambda: f"res-{uuid.uuid4().hex[:12]}",
        min_length=1,
        max_length=64,
    )
    full_name: str = Field(..., min_length=1, max_length=120)
    age: Optional[int] = Field(default=None, ge=0, le=130)
    address_location: str = Field(..., min_length=1, max_length=255, alias="location")
    associated_node_id: Optional[str] = Field(default=None, max_length=64)
    safety_information: Optional[str] = Field(default=None, max_length=500)
    consent_status: ConsentStatus = Field(default=ConsentStatus.GRANTED)
    active_status: bool = Field(default=True)

    @model_validator(mode="before")
    @classmethod
    def _accept_address_or_location(cls, data: Any) -> Any:
        if isinstance(data, dict):
            copied = dict(data)
            if "address_location" not in copied:
                if "address" in copied:
                    copied["address_location"] = copied.pop("address")
                elif "location" in copied:
                    copied["address_location"] = copied.pop("location")
            return copied
        return data

    @field_validator("resident_id")
    @classmethod
    def _validate_resident_id(cls, v: str) -> str:
        return validate_identifier(v, "resident_id")

    @field_validator("full_name", "address_location")
    @classmethod
    def _strip_non_empty(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty or whitespace only")
        return cleaned

    @field_validator("associated_node_id")
    @classmethod
    def _validate_node_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return validate_identifier(v, "associated_node_id")

    @field_validator("consent_status", mode="before")
    @classmethod
    def _validate_consent(cls, v: Any) -> ConsentStatus:
        return _normalize_consent(v)


class ResidentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    full_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    age: Optional[int] = Field(default=None, ge=0, le=130)
    address_location: Optional[str] = Field(default=None, min_length=1, max_length=255)
    associated_node_id: Optional[str] = Field(default=None, max_length=64)
    safety_information: Optional[str] = Field(default=None, max_length=500)
    consent_status: Optional[ConsentStatus] = Field(default=None)
    active_status: Optional[bool] = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def _accept_address_or_location(cls, data: Any) -> Any:
        if isinstance(data, dict):
            copied = dict(data)
            if "address_location" not in copied:
                if "address" in copied:
                    copied["address_location"] = copied.pop("address")
                elif "location" in copied:
                    copied["address_location"] = copied.pop("location")
            return copied
        return data

    @field_validator("full_name", "address_location")
    @classmethod
    def _strip_optional(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty or whitespace only")
        return cleaned

    @field_validator("associated_node_id")
    @classmethod
    def _validate_node_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return validate_identifier(v, "associated_node_id")

    @field_validator("consent_status", mode="before")
    @classmethod
    def _validate_consent(cls, v: Any) -> Optional[ConsentStatus]:
        if v is None:
            return None
        return _normalize_consent(v)


class ResidentResponse(BaseModel):
    """
    Public resident response schema.
    By default, optional `safety_information` is excluded (`None`) unless
    explicitly requested via access-controlled retrieval (`include_safety_info=True`),
    preventing accidental exposure of sensitive resident safety notes.
    """

    model_config = ConfigDict(from_attributes=True)

    resident_id: str
    full_name: str
    age: Optional[int] = None
    address_location: str
    associated_node_id: Optional[str] = None
    has_safety_information: bool = False
    safety_information: Optional[str] = None
    consent_status: ConsentStatus
    active_status: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# 2. Emergency Contact Schemas
# ---------------------------------------------------------------------------


class EmergencyContactCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contact_id: str = Field(
        default_factory=lambda: f"cnt-{uuid.uuid4().hex[:12]}",
        min_length=1,
        max_length=64,
    )
    resident_id: str = Field(..., min_length=1, max_length=64)
    full_name: str = Field(..., min_length=1, max_length=120)
    phone_number: str = Field(..., min_length=8, max_length=16)
    relationship: str = Field(..., min_length=1, max_length=64)
    priority: int = Field(default=1, ge=1, le=100)
    preferred_channels: List[NotificationChannel] = Field(
        default_factory=lambda: [NotificationChannel.SMS, NotificationChannel.VOICE_CALL],
        min_length=1,
    )
    consent_status: ConsentStatus = Field(default=ConsentStatus.GRANTED)
    active_status: bool = Field(default=True)

    @field_validator("contact_id")
    @classmethod
    def _validate_contact_id(cls, v: str) -> str:
        return validate_identifier(v, "contact_id")

    @field_validator("resident_id")
    @classmethod
    def _validate_resident_id(cls, v: str) -> str:
        return validate_identifier(v, "resident_id")

    @field_validator("full_name", "relationship")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty or whitespace only")
        return cleaned

    @field_validator("phone_number")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        return validate_e164_phone(v)

    @field_validator("preferred_channels")
    @classmethod
    def _deduplicate_channels(cls, v: List[NotificationChannel]) -> List[NotificationChannel]:
        if not v:
            raise ValueError("At least one preferred notification channel is required")
        seen: List[NotificationChannel] = []
        for ch in v:
            if ch not in seen:
                seen.append(ch)
        return seen

    @field_validator("consent_status", mode="before")
    @classmethod
    def _validate_consent(cls, v: Any) -> ConsentStatus:
        return _normalize_consent(v)


class EmergencyContactUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    phone_number: Optional[str] = Field(default=None, min_length=8, max_length=16)
    relationship: Optional[str] = Field(default=None, min_length=1, max_length=64)
    priority: Optional[int] = Field(default=None, ge=1, le=100)
    preferred_channels: Optional[List[NotificationChannel]] = Field(default=None, min_length=1)
    consent_status: Optional[ConsentStatus] = Field(default=None)
    active_status: Optional[bool] = Field(default=None)

    @field_validator("full_name", "relationship")
    @classmethod
    def _strip_optional(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty")
        return cleaned

    @field_validator("phone_number")
    @classmethod
    def _validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return validate_e164_phone(v)

    @field_validator("consent_status", mode="before")
    @classmethod
    def _validate_consent(cls, v: Any) -> Optional[ConsentStatus]:
        if v is None:
            return None
        return _normalize_consent(v)


class EmergencyContactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    contact_id: str
    resident_id: str
    full_name: str
    phone_number: str
    relationship: str
    priority: int
    preferred_channels: List[NotificationChannel]
    consent_status: ConsentStatus
    active_status: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# 3. Registered Node Schemas
# ---------------------------------------------------------------------------


class NodeRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., min_length=1, max_length=64)
    node_name: str = Field(..., min_length=1, max_length=120)
    location: str = Field(..., min_length=1, max_length=255)
    operational_status: NodeOperationalStatus = Field(default=NodeOperationalStatus.ONLINE)
    resident_id: Optional[str] = Field(default=None, max_length=64)

    @field_validator("node_id")
    @classmethod
    def _validate_node_id(cls, v: str) -> str:
        return validate_identifier(v, "node_id")

    @field_validator("node_name", "location")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty")
        return cleaned

    @field_validator("resident_id")
    @classmethod
    def _validate_resident_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return validate_identifier(v, "resident_id")


class NodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    node_id: str
    node_name: str
    location: str
    operational_status: NodeOperationalStatus
    resident_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    # Optional runtime fields populated when bridged with in-memory NodeRegistry
    runtime_status: Optional[str] = None
    last_seen: Optional[datetime] = None
    total_readings: Optional[int] = None


# ---------------------------------------------------------------------------
# 4. Actuator Schemas
# ---------------------------------------------------------------------------


class ActuatorRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actuator_id: str = Field(..., min_length=1, max_length=64)
    associated_node_id: str = Field(..., min_length=1, max_length=64)
    actuator_type: str = Field(default="ESP32_FAN_5V_UNFILTERED", min_length=1, max_length=64)
    device_name: str = Field(..., min_length=1, max_length=120)
    ip_address: Optional[str] = Field(default=None, max_length=64)
    connection_status: ActuatorConnectionStatus = Field(default=ActuatorConnectionStatus.OFFLINE)
    current_state: ActuatorState = Field(default=ActuatorState.OFF)
    last_heartbeat: Optional[datetime] = Field(default=None)

    @field_validator("actuator_id")
    @classmethod
    def _validate_actuator_id(cls, v: str) -> str:
        return validate_identifier(v, "actuator_id")

    @field_validator("associated_node_id")
    @classmethod
    def _validate_node_id(cls, v: str) -> str:
        return validate_identifier(v, "associated_node_id")

    @field_validator("actuator_type", "device_name")
    @classmethod
    def _strip_text(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Field cannot be empty")
        return cleaned

    @field_validator("ip_address")
    @classmethod
    def _validate_ip(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        cleaned = v.strip()
        try:
            ipaddress.ip_address(cleaned)
        except ValueError as exc:
            raise ValueError(f"Invalid IP address '{v}'") from exc
        return cleaned

    @field_validator("last_heartbeat")
    @classmethod
    def _normalize_hb(cls, v: Optional[datetime]) -> Optional[datetime]:
        return ensure_utc(v)


class ActuatorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    actuator_id: str
    associated_node_id: str
    actuator_type: str
    device_name: str
    ip_address: Optional[str] = None
    connection_status: ActuatorConnectionStatus
    current_state: ActuatorState
    last_heartbeat: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# 5. Emergency Event Schemas
# ---------------------------------------------------------------------------


class EmergencyEventCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(
        default_factory=lambda: f"emg-{uuid.uuid4().hex[:12]}",
        min_length=1,
        max_length=64,
    )
    associated_node_id: str = Field(..., min_length=1, max_length=64)
    resident_id: Optional[str] = Field(default=None, max_length=64)
    event_type: str = Field(..., min_length=1, max_length=64)
    severity: EmergencySeverity = Field(..., description="LOW, MEDIUM, HIGH, or CRITICAL")
    event_status: EmergencyEventStatus = Field(default=EmergencyEventStatus.DETECTED)
    detected_at: datetime = Field(default_factory=utc_now)
    acknowledged_at: Optional[datetime] = Field(default=None)
    resolved_at: Optional[datetime] = Field(default=None)
    event_metadata: Dict[str, Any] = Field(default_factory=dict)
    escalation_level: int = Field(default=1, ge=0, le=10)
    # Phase 2 backward-compatible structured policy fields
    decision_reason: Optional[str] = Field(default=None, max_length=1000)
    supporting_measurements: Dict[str, Any] = Field(default_factory=dict)
    model_uncertainty: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    recommended_actions: List[str] = Field(default_factory=list)
    decision_timestamp: Optional[datetime] = Field(default=None)
    human_intervention_required: bool = Field(default=False)

    @field_validator("event_id")
    @classmethod
    def _validate_event_id(cls, v: str) -> str:
        return validate_identifier(v, "event_id")

    @field_validator("associated_node_id")
    @classmethod
    def _validate_node_id(cls, v: str) -> str:
        return validate_identifier(v, "associated_node_id")

    @field_validator("resident_id")
    @classmethod
    def _validate_resident_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return validate_identifier(v, "resident_id")

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("event_type cannot be empty")
        return cleaned

    @field_validator("detected_at", "acknowledged_at", "resolved_at", "decision_timestamp")
    @classmethod
    def _normalize_timestamps(cls, v: Optional[datetime]) -> Optional[datetime]:
        return ensure_utc(v)


class EmergencyEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    associated_node_id: str
    resident_id: Optional[str] = None
    event_type: str
    severity: EmergencySeverity
    event_status: EmergencyEventStatus
    detected_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    event_metadata: Dict[str, Any] = Field(default_factory=dict)
    escalation_level: int
    decision_reason: Optional[str] = None
    supporting_measurements: Dict[str, Any] = Field(default_factory=dict)
    model_uncertainty: Optional[float] = None
    recommended_actions: List[str] = Field(default_factory=list)
    decision_timestamp: Optional[datetime] = None
    human_intervention_required: bool = False


# ---------------------------------------------------------------------------
# 6. Emergency Notification Schemas
# ---------------------------------------------------------------------------


class NotificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    notification_id: str = Field(
        default_factory=lambda: f"ntf-{uuid.uuid4().hex[:12]}",
        min_length=1,
        max_length=64,
    )
    event_id: str = Field(..., min_length=1, max_length=64)
    contact_id: str = Field(..., min_length=1, max_length=64)
    notification_channel: NotificationChannel
    provider: str = Field(default="TWILIO", min_length=1, max_length=64)
    delivery_status: NotificationDeliveryStatus = Field(
        default=NotificationDeliveryStatus.QUEUED
    )
    acknowledgement_status: HumanAcknowledgementStatus = Field(
        default=HumanAcknowledgementStatus.PENDING
    )
    provider_reference_id: Optional[str] = Field(default=None, max_length=128)
    sent_at: Optional[datetime] = Field(default=None)
    delivered_at: Optional[datetime] = Field(default=None)
    acknowledged_at: Optional[datetime] = Field(default=None)
    failure_reason: Optional[str] = Field(default=None, max_length=500)

    @field_validator("notification_id")
    @classmethod
    def _validate_ntf_id(cls, v: str) -> str:
        return validate_identifier(v, "notification_id")

    @field_validator("event_id")
    @classmethod
    def _validate_event_id(cls, v: str) -> str:
        return validate_identifier(v, "event_id")

    @field_validator("contact_id")
    @classmethod
    def _validate_contact_id(cls, v: str) -> str:
        return validate_identifier(v, "contact_id")

    @field_validator("provider")
    @classmethod
    def _strip_provider(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("provider cannot be empty")
        return cleaned

    @field_validator("sent_at", "delivered_at", "acknowledged_at")
    @classmethod
    def _normalize_timestamps(cls, v: Optional[datetime]) -> Optional[datetime]:
        return ensure_utc(v)


class NotificationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    notification_id: str
    event_id: str
    contact_id: str
    notification_channel: NotificationChannel
    provider: str
    delivery_status: NotificationDeliveryStatus
    acknowledgement_status: HumanAcknowledgementStatus
    provider_reference_id: Optional[str] = None
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# 7. Actuator Command Log Schemas
# ---------------------------------------------------------------------------


class ActuatorCommandLog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    command_id: str = Field(
        default_factory=lambda: f"cmd-{uuid.uuid4().hex[:12]}",
        min_length=1,
        max_length=64,
    )
    actuator_id: str = Field(..., min_length=1, max_length=64)
    event_id: Optional[str] = Field(default=None, max_length=64)
    command: str = Field(..., min_length=1, max_length=64)
    requested_at: datetime = Field(default_factory=utc_now)
    acknowledged_at: Optional[datetime] = Field(default=None)
    execution_status: CommandExecutionStatus = Field(
        default=CommandExecutionStatus.PENDING
    )
    error_details: Optional[str] = Field(default=None, max_length=500)

    @field_validator("command_id")
    @classmethod
    def _validate_cmd_id(cls, v: str) -> str:
        return validate_identifier(v, "command_id")

    @field_validator("actuator_id")
    @classmethod
    def _validate_actuator_id(cls, v: str) -> str:
        return validate_identifier(v, "actuator_id")

    @field_validator("event_id")
    @classmethod
    def _validate_event_id(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return None
        return validate_identifier(v, "event_id")

    @field_validator("command")
    @classmethod
    def _strip_command(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("command cannot be empty")
        return cleaned

    @field_validator("requested_at", "acknowledged_at")
    @classmethod
    def _normalize_timestamps(cls, v: Optional[datetime]) -> Optional[datetime]:
        return ensure_utc(v)


class ActuatorCommandResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    command_id: str
    actuator_id: str
    event_id: Optional[str] = None
    command: str
    requested_at: datetime
    acknowledged_at: Optional[datetime] = None
    execution_status: CommandExecutionStatus
    error_details: Optional[str] = None

