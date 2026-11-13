"""
Phase 3: Wireless ESP32 Actuator Service & Transport Layer.

Orchestrates validated commands between the UNO Q Intelligence Server and
NodeMCU ESP-32S V1.1 actuators over Wi-Fi LAN HTTP REST, reusing Phase 1
`EmergencyDatabase` tables (`actuators` and `actuator_command_logs`) and
enforcing Phase 2 safety rules (never activating an unfiltered fan for
particulate removal in real environmental protection mode).
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import httpx

from app.emergency.actuator_schemas import (
    ActuatorAckStatus,
    ActuatorCommandAck,
    ActuatorCommandPayload,
    ActuatorCommandType,
    ActuatorControlMode,
    ActuatorDispatchResult,
    ActuatorHeartbeatRequest,
    ActuatorHeartbeatResponse,
    ActuatorPhysicalOutputState,
)
from app.emergency.database import EmergencyDatabase, RecordNotFoundError
from app.emergency.decision_schemas import (
    EventLifecycleTransition,
    PolicyDecisionResult,
)
from app.emergency.response_policy import (
    is_actuator_alert_light,
    is_actuator_filtration_capable,
    is_diagnostic_hazard_type,
    is_qualifying_environmental_hazard,
)
from app.emergency.schemas import (
    ActuatorCommandLog,
    ActuatorConnectionStatus,
    ActuatorRegistration,
    ActuatorResponse,
    ActuatorState,
    CommandExecutionStatus,
    EmergencyEventResponse,
    EmergencyEventStatus,
    NodeRegistration,
    ensure_utc,
    utc_now,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transport Exceptions & Interface
# ---------------------------------------------------------------------------


class ActuatorTransportError(Exception):
    """Base error raised by an actuator transport implementation."""


class ActuatorTimeoutError(ActuatorTransportError):
    """Raised when an ESP32 actuator does not respond within the timeout."""


class ActuatorUnreachableError(ActuatorTransportError):
    """Raised when the ESP32 actuator cannot be reached on the network."""


class ActuatorProtocolError(ActuatorTransportError):
    """Raised when the ESP32 returns a malformed or non-2xx response."""


class ActuatorTransport(ABC):
    """Abstract transport interface for sending validated commands to an ESP32."""

    @abstractmethod
    async def send_command(
        self,
        actuator: ActuatorResponse,
        payload: ActuatorCommandPayload,
        timeout_s: float,
    ) -> ActuatorCommandAck:
        """Send a command payload to the target actuator and return its ack."""


class HttpEsp32ActuatorTransport(ActuatorTransport):
    """
    HTTP REST transport over local Wi-Fi LAN (`POST http://{ip}:{port}/actuator/command`).
    """

    def __init__(self, port: int = 8080) -> None:
        self.port = port

    async def send_command(
        self,
        actuator: ActuatorResponse,
        payload: ActuatorCommandPayload,
        timeout_s: float,
    ) -> ActuatorCommandAck:
        if not actuator.ip_address:
            raise ActuatorUnreachableError(
                f"Actuator '{actuator.actuator_id}' has no registered IP address"
            )

        url = f"http://{actuator.ip_address}:{self.port}/actuator/command"
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                response = await client.post(url, json=payload.model_dump(mode="json"))
        except httpx.TimeoutException as exc:
            raise ActuatorTimeoutError(
                f"Command '{payload.command_id}' to '{actuator.actuator_id}' timed out after {timeout_s}s"
            ) from exc
        except httpx.RequestError as exc:
            raise ActuatorUnreachableError(
                f"Failed to reach actuator '{actuator.actuator_id}' at {url}: {exc}"
            ) from exc

        if response.status_code >= 400:
            raise ActuatorProtocolError(
                f"Actuator '{actuator.actuator_id}' returned HTTP {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
            return ActuatorCommandAck.model_validate(data)
        except Exception as exc:
            raise ActuatorProtocolError(
                f"Invalid JSON acknowledgement from '{actuator.actuator_id}': {exc}"
            ) from exc


class MockActuatorTransport(ActuatorTransport):
    """
    Deterministic in-memory mock transport for automated testing without
    physical NodeMCU ESP-32S V1.1 hardware.
    """

    def __init__(
        self,
        *,
        physical_driver_verified: bool = False,
        simulate_timeout: bool = False,
        simulate_unreachable: bool = False,
        override_ack_actuator_id: Optional[str] = None,
        override_ack_command_id: Optional[str] = None,
    ) -> None:
        self.physical_driver_verified = physical_driver_verified
        self.simulate_timeout = simulate_timeout
        self.simulate_unreachable = simulate_unreachable
        self.override_ack_actuator_id = override_ack_actuator_id
        self.override_ack_command_id = override_ack_command_id
        self.sent_payloads: List[ActuatorCommandPayload] = []
        self.output_states: Dict[str, ActuatorPhysicalOutputState] = {}

    async def send_command(
        self,
        actuator: ActuatorResponse,
        payload: ActuatorCommandPayload,
        timeout_s: float,
    ) -> ActuatorCommandAck:
        self.sent_payloads.append(payload)

        if self.simulate_timeout:
            raise ActuatorTimeoutError(
                f"Simulated timeout for command '{payload.command_id}'"
            )
        if self.simulate_unreachable:
            raise ActuatorUnreachableError(
                f"Simulated unreachable actuator '{actuator.actuator_id}'"
            )

        ack_actuator_id = self.override_ack_actuator_id or actuator.actuator_id
        ack_command_id = self.override_ack_command_id or payload.command_id

        current = self.output_states.get(
            actuator.actuator_id,
            ActuatorPhysicalOutputState.OFF
            if self.physical_driver_verified
            else ActuatorPhysicalOutputState.SAFE_LOCKED_OFF,
        )

        if payload.command in (
            ActuatorCommandType.FAN_ON,
            ActuatorCommandType.LIGHT_ON,
        ):
            if self.physical_driver_verified:
                current = ActuatorPhysicalOutputState.ON
                status = ActuatorAckStatus.EXECUTED
            else:
                current = ActuatorPhysicalOutputState.SAFE_LOCKED_OFF
                status = ActuatorAckStatus.ACKNOWLEDGED
        elif payload.command in (
            ActuatorCommandType.FAN_OFF,
            ActuatorCommandType.LIGHT_OFF,
            ActuatorCommandType.EMERGENCY_STOP,
        ):
            current = (
                ActuatorPhysicalOutputState.OFF
                if self.physical_driver_verified
                else ActuatorPhysicalOutputState.SAFE_LOCKED_OFF
            )
            status = ActuatorAckStatus.EXECUTED
        else:  # GET_STATUS
            status = ActuatorAckStatus.EXECUTED

        self.output_states[actuator.actuator_id] = current
        return ActuatorCommandAck(
            command_id=ack_command_id,
            actuator_id=ack_actuator_id,
            status=status,
            output_state=current,
            physical_driver_verified=self.physical_driver_verified,
            timestamp=utc_now(),
        )


# ---------------------------------------------------------------------------
# State Mapping Helpers
# ---------------------------------------------------------------------------


def _map_physical_output_to_db_state(
    output_state: ActuatorPhysicalOutputState,
) -> ActuatorState:
    if output_state == ActuatorPhysicalOutputState.ON:
        return ActuatorState.ON
    if output_state in (
        ActuatorPhysicalOutputState.OFF,
        ActuatorPhysicalOutputState.SAFE_LOCKED_OFF,
    ):
        return ActuatorState.OFF
    if output_state == ActuatorPhysicalOutputState.FAILSAFE_OFF:
        return ActuatorState.FAILSAFE_OFF
    return ActuatorState.UNKNOWN


def _map_ack_status_to_execution_status(
    ack_status: ActuatorAckStatus,
) -> CommandExecutionStatus:
    mapping = {
        ActuatorAckStatus.ACKNOWLEDGED: CommandExecutionStatus.ACKNOWLEDGED,
        ActuatorAckStatus.EXECUTED: CommandExecutionStatus.EXECUTED,
        ActuatorAckStatus.REJECTED: CommandExecutionStatus.REJECTED,
        ActuatorAckStatus.ERROR: CommandExecutionStatus.FAILED,
    }
    return mapping[ack_status]


# ---------------------------------------------------------------------------
# ActuatorService
# ---------------------------------------------------------------------------


class ActuatorService:
    """
    Backend service for ESP32 wireless actuator registration, heartbeats,
    safety-gated command dispatch, duplicate suppression, and policy integration.
    """

    def __init__(
        self,
        emergency_db: EmergencyDatabase,
        transport: Optional[ActuatorTransport] = None,
        *,
        esp32_port: int = 8080,
        command_timeout_s: float = 5.0,
        heartbeat_stale_s: float = 90.0,
        duplicate_window_s: float = 30.0,
        default_lease_s: int = 60,
        demo_mode_enabled: bool = False,
        alert_light_on_diagnostic: bool = False,
    ) -> None:
        self.db = emergency_db
        self.transport: ActuatorTransport = transport or HttpEsp32ActuatorTransport(
            port=esp32_port
        )
        self.command_timeout_s = command_timeout_s
        self.heartbeat_stale_s = heartbeat_stale_s
        self.duplicate_window_s = duplicate_window_s
        self.default_lease_s = default_lease_s
        self.demo_mode_enabled = demo_mode_enabled
        self.alert_light_on_diagnostic = alert_light_on_diagnostic

    def _resolve_heartbeat_node_id(
        self,
        requested_node_id: str,
        node_registry: Optional[object] = None,
    ) -> str:
        """
        Resolve `associated_node_id` from an ESP32 heartbeat, bridging the legacy
        'node-01' default with UNO Q's 'uno-q-001' primary node ID without
        breaking explicit node registrations or foreign-key enforcement.
        """
        if self.db.get_node(requested_node_id) is not None:
            return requested_node_id

        has_in_registry = bool(
            node_registry is not None
            and hasattr(node_registry, "has_node")
            and node_registry.has_node(requested_node_id)
        )

        if requested_node_id in ("uno-q-001", "node-01"):
            if self.db.get_node("uno-q-001") is None:
                self.db.register_node(
                    NodeRegistration(
                        node_id="uno-q-001",
                        node_name="Arduino UNO Q Primary Node",
                        location="Local Edge Node",
                    )
                )
                logger.info(
                    "Auto-registered primary UNO Q node 'uno-q-001' during ESP32 heartbeat (%s)",
                    requested_node_id,
                )
            if requested_node_id == "node-01":
                logger.info(
                    "Aliasing ESP32 heartbeat node_id 'node-01' -> 'uno-q-001'"
                )
            return "uno-q-001"

        if has_in_registry:
            self.db.register_node(
                NodeRegistration(
                    node_id=requested_node_id,
                    node_name=f"Edge Node {requested_node_id}",
                    location="Local Edge Node",
                )
            )
            return requested_node_id

        return requested_node_id

    def register_or_heartbeat(
        self,
        req: ActuatorHeartbeatRequest,
        *,
        node_registry: Optional[object] = None,
    ) -> ActuatorResponse:
        """
        Register a new ESP32 actuator or update heartbeat/state for an existing
        one in `EmergencyDatabase.actuators`.
        """
        db_state = _map_physical_output_to_db_state(req.output_state)
        existing = self.db.get_actuator(req.actuator_id)
        resolved_node_id = self._resolve_heartbeat_node_id(
            req.associated_node_id, node_registry=node_registry
        )
        if existing is not None:
            if existing.associated_node_id != resolved_node_id:
                if (
                    existing.associated_node_id == "uno-q-001"
                    and req.associated_node_id == "node-01"
                ):
                    resolved_node_id = "uno-q-001"
                else:
                    raise ValueError(
                        f"Actuator '{req.actuator_id}' is bound to node "
                        f"'{existing.associated_node_id}', not '{req.associated_node_id}'"
                    )
            return self.db.update_actuator_heartbeat(
                actuator_id=req.actuator_id,
                current_state=db_state,
                connection_status=ActuatorConnectionStatus.ONLINE,
                ip_address=req.ip_address,
                heartbeat_at=req.timestamp,
            )

        registration = ActuatorRegistration(
            actuator_id=req.actuator_id,
            associated_node_id=resolved_node_id,
            actuator_type=req.actuator_type,
            device_name=req.device_name,
            ip_address=req.ip_address,
            connection_status=ActuatorConnectionStatus.ONLINE,
            current_state=db_state,
            last_heartbeat=req.timestamp,
        )
        return self.db.register_actuator(registration)

    def get_unresolved_alert_events(
        self, node_id: str
    ) -> List[EmergencyEventResponse]:
        """Return unresolved events on `node_id` that qualify to keep an alert light ON."""
        if not self.db.is_initialized:
            return []
        events = self.db.list_emergency_events(node_id=node_id)
        active: List[EmergencyEventResponse] = []
        for ev in events:
            if ev.event_status in (
                EmergencyEventStatus.RESOLVED,
                EmergencyEventStatus.CANCELLED,
            ):
                continue
            if (
                not self.alert_light_on_diagnostic
                and is_diagnostic_hazard_type(ev.event_type)
            ):
                continue
            active.append(ev)
        return active

    def build_heartbeat_response(
        self,
        actuator: ActuatorResponse,
        *,
        system_ready: bool = True,
    ) -> ActuatorHeartbeatResponse:
        """
        Construct the authoritative heartbeat response including `desired_state`
        so rebooting ESP32 alert lights recover immediately from active events.
        """
        desired_state = ActuatorPhysicalOutputState.OFF
        active_event_id: Optional[str] = None
        active_event_count = 0
        severity: Optional[str] = None
        alert_type: Optional[str] = None

        if is_actuator_alert_light(actuator.actuator_type):
            unresolved = self.get_unresolved_alert_events(actuator.associated_node_id)
            active_event_count = len(unresolved)
            if unresolved:
                top = unresolved[0]
                desired_state = ActuatorPhysicalOutputState.ON
                active_event_id = top.event_id
                severity = (
                    top.severity.value
                    if hasattr(top.severity, "value")
                    else str(top.severity)
                )
                alert_type = top.event_type
        elif actuator.current_state == ActuatorState.ON:
            desired_state = ActuatorPhysicalOutputState.ON

        return ActuatorHeartbeatResponse(
            **actuator.model_dump(),
            system_ready=system_ready,
            desired_state=desired_state,
            active_event_id=active_event_id,
            active_event_count=active_event_count,
            severity=severity,
            alert_type=alert_type,
        )

    def mark_stale_actuators_offline(
        self, node_id: Optional[str] = None, now: Optional[datetime] = None
    ) -> List[ActuatorResponse]:
        """Mark ONLINE actuators whose heartbeat exceeded `heartbeat_stale_s` as OFFLINE."""
        ref_now = ensure_utc(now) or utc_now()
        cutoff = ref_now - timedelta(seconds=self.heartbeat_stale_s)
        updated: List[ActuatorResponse] = []

        if node_id is not None:
            actuators = self.db.list_actuators_for_node(node_id)
        else:
            actuators = []
            for node in self.db.list_nodes():
                actuators.extend(self.db.list_actuators_for_node(node.node_id))

        for act in actuators:
            if (
                act.connection_status == ActuatorConnectionStatus.ONLINE
                and (act.last_heartbeat is None or ensure_utc(act.last_heartbeat) < cutoff)
            ):
                updated.append(
                    self.db.update_actuator_heartbeat(
                        actuator_id=act.actuator_id,
                        current_state=act.current_state,
                        connection_status=ActuatorConnectionStatus.OFFLINE,
                        heartbeat_at=act.last_heartbeat,
                    )
                )
        return updated

    def _is_duplicate_command(
        self,
        actuator: ActuatorResponse,
        command: ActuatorCommandType,
        command_id: str,
        now: datetime,
    ) -> Optional[str]:
        if self.db.get_actuator_command_log(command_id) is not None:
            return f"Duplicate command_id '{command_id}' already logged"

        if command in (ActuatorCommandType.EMERGENCY_STOP, ActuatorCommandType.GET_STATUS):
            return None

        target_state = (
            ActuatorState.ON
            if command in (ActuatorCommandType.FAN_ON, ActuatorCommandType.LIGHT_ON)
            else ActuatorState.OFF
        )
        if actuator.current_state != target_state:
            return None

        recent_logs = self.db.list_command_logs_for_actuator(actuator.actuator_id)
        window_start = now - timedelta(seconds=self.duplicate_window_s)
        for log in recent_logs[:10]:
            req_at = ensure_utc(log.requested_at)
            if req_at is None or req_at < window_start:
                continue
            if (
                log.command == command.value
                and log.execution_status
                in (
                    CommandExecutionStatus.EXECUTED,
                    CommandExecutionStatus.ACKNOWLEDGED,
                )
            ):
                return (
                    f"Duplicate '{command.value}' suppressed: actuator already "
                    f"{actuator.current_state.value} and acknowledged within {self.duplicate_window_s:.0f}s"
                )
        return None

    async def dispatch_command(
        self,
        actuator_id: str,
        command: ActuatorCommandType,
        *,
        control_mode: ActuatorControlMode = ActuatorControlMode.PROTECTION_MODE,
        event_id: Optional[str] = None,
        command_id: Optional[str] = None,
        lease_seconds: Optional[int] = None,
        reason: Optional[str] = None,
    ) -> ActuatorDispatchResult:
        """
        Validate, log, and dispatch a command to an ESP32 actuator.
        Enforces unfiltered-fan safety in `PROTECTION_MODE`, duplicate suppression,
        device identity validation, and timeout/error recording.
        """
        actuator = self.db.get_actuator(actuator_id)
        if actuator is None:
            raise RecordNotFoundError(f"Actuator '{actuator_id}' not found")

        now = utc_now()
        effective_cmd_id = command_id or f"cmd-{uuid.uuid4().hex[:12]}"
        effective_lease = lease_seconds or self.default_lease_s

        # Reject commands incompatible with actuator hardware type
        is_light = is_actuator_alert_light(actuator.actuator_type)
        if (
            is_light
            and command in (ActuatorCommandType.FAN_ON, ActuatorCommandType.FAN_OFF)
        ) or (
            not is_light
            and command in (ActuatorCommandType.LIGHT_ON, ActuatorCommandType.LIGHT_OFF)
        ):
            rejection_msg = (
                f"Incompatible command '{command.value}' for actuator '{actuator_id}' "
                f"(type={actuator.actuator_type})"
            )
            log = self.db.create_actuator_command_log(
                ActuatorCommandLog(
                    command_id=effective_cmd_id,
                    actuator_id=actuator_id,
                    event_id=event_id,
                    command=command.value,
                    requested_at=now,
                    execution_status=CommandExecutionStatus.REJECTED,
                    error_details=rejection_msg,
                )
            )
            logger.warning(rejection_msg)
            return ActuatorDispatchResult(
                dispatched=False,
                suppressed=True,
                suppression_reason=rejection_msg,
                control_mode=control_mode,
                command_log=log,
                actuator=actuator,
            )

        # Safety Rule: Never activate an unfiltered fan automatically in PROTECTION_MODE
        if (
            command == ActuatorCommandType.FAN_ON
            and control_mode == ActuatorControlMode.PROTECTION_MODE
            and not is_actuator_filtration_capable(actuator.actuator_type)
        ):
            suppression_msg = (
                f"Blocked automated FAN_ON in PROTECTION_MODE: actuator '{actuator_id}' "
                f"(type={actuator.actuator_type}) is not filtration-capable"
            )
            log = self.db.create_actuator_command_log(
                ActuatorCommandLog(
                    command_id=effective_cmd_id,
                    actuator_id=actuator_id,
                    event_id=event_id,
                    command=command.value,
                    requested_at=now,
                    execution_status=CommandExecutionStatus.REJECTED,
                    error_details=suppression_msg,
                )
            )
            logger.warning(suppression_msg)
            return ActuatorDispatchResult(
                dispatched=False,
                suppressed=True,
                suppression_reason=suppression_msg,
                control_mode=control_mode,
                command_log=log,
                actuator=actuator,
            )

        # Duplicate command protection
        dup_reason = self._is_duplicate_command(actuator, command, effective_cmd_id, now)
        if dup_reason is not None:
            return ActuatorDispatchResult(
                dispatched=False,
                suppressed=True,
                suppression_reason=dup_reason,
                control_mode=control_mode,
                actuator=actuator,
            )

        # Offline actuator check
        if actuator.connection_status == ActuatorConnectionStatus.OFFLINE:
            err_msg = f"Actuator '{actuator_id}' is OFFLINE; command '{command.value}' not sent"
            log = self.db.create_actuator_command_log(
                ActuatorCommandLog(
                    command_id=effective_cmd_id,
                    actuator_id=actuator_id,
                    event_id=event_id,
                    command=command.value,
                    requested_at=now,
                    execution_status=CommandExecutionStatus.FAILED,
                    error_details=err_msg,
                )
            )
            return ActuatorDispatchResult(
                dispatched=False,
                suppressed=False,
                suppression_reason=err_msg,
                control_mode=control_mode,
                command_log=log,
                actuator=actuator,
            )

        # Persist PENDING command log before network I/O
        self.db.create_actuator_command_log(
            ActuatorCommandLog(
                command_id=effective_cmd_id,
                actuator_id=actuator_id,
                event_id=event_id,
                command=command.value,
                requested_at=now,
                execution_status=CommandExecutionStatus.PENDING,
                error_details=reason,
            )
        )

        payload = ActuatorCommandPayload(
            command_id=effective_cmd_id,
            node_id=actuator.associated_node_id,
            actuator_id=actuator.actuator_id,
            command=command,
            event_id=event_id,
            control_mode=control_mode,
            lease_seconds=effective_lease,
            timestamp=now,
        )

        try:
            ack = await self.transport.send_command(
                actuator=actuator,
                payload=payload,
                timeout_s=self.command_timeout_s,
            )
        except ActuatorTimeoutError as exc:
            err = str(exc)
            updated_log = self.db.update_actuator_command_status(
                command_id=effective_cmd_id,
                execution_status=CommandExecutionStatus.TIMED_OUT,
                error_details=err,
            )
            updated_act = self.db.update_actuator_heartbeat(
                actuator_id=actuator_id,
                current_state=ActuatorState.UNKNOWN,
                connection_status=ActuatorConnectionStatus.OFFLINE,
                heartbeat_at=actuator.last_heartbeat,
            )
            return ActuatorDispatchResult(
                dispatched=False,
                control_mode=control_mode,
                command_log=updated_log,
                actuator=updated_act,
            )
        except ActuatorTransportError as exc:
            err = str(exc)
            updated_log = self.db.update_actuator_command_status(
                command_id=effective_cmd_id,
                execution_status=CommandExecutionStatus.FAILED,
                error_details=err,
            )
            updated_act = self.db.update_actuator_heartbeat(
                actuator_id=actuator_id,
                current_state=actuator.current_state,
                connection_status=ActuatorConnectionStatus.OFFLINE,
                heartbeat_at=actuator.last_heartbeat,
            )
            return ActuatorDispatchResult(
                dispatched=False,
                control_mode=control_mode,
                command_log=updated_log,
                actuator=updated_act,
            )

        # Device identity & command_id validation on acknowledgement
        if ack.actuator_id != actuator.actuator_id or ack.command_id != effective_cmd_id:
            err = (
                f"Device identity mismatch in ack: expected "
                f"({actuator.actuator_id}, {effective_cmd_id}), got "
                f"({ack.actuator_id}, {ack.command_id})"
            )
            updated_log = self.db.update_actuator_command_status(
                command_id=effective_cmd_id,
                execution_status=CommandExecutionStatus.FAILED,
                error_details=err,
            )
            return ActuatorDispatchResult(
                dispatched=False,
                control_mode=control_mode,
                command_log=updated_log,
                acknowledgement=ack,
                actuator=actuator,
            )

        exec_status = _map_ack_status_to_execution_status(ack.status)
        updated_log = self.db.update_actuator_command_status(
            command_id=effective_cmd_id,
            execution_status=exec_status,
            acknowledged_at=ack.timestamp,
            error_details=ack.error_details,
        )
        updated_act = self.db.update_actuator_heartbeat(
            actuator_id=actuator_id,
            current_state=_map_physical_output_to_db_state(ack.output_state),
            connection_status=ActuatorConnectionStatus.ONLINE,
            heartbeat_at=ack.timestamp,
        )
        return ActuatorDispatchResult(
            dispatched=True,
            control_mode=control_mode,
            command_log=updated_log,
            acknowledgement=ack,
            actuator=updated_act,
        )

    async def sync_light_for_node(
        self,
        node_id: str,
        *,
        event_id: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> List[ActuatorDispatchResult]:
        """
        Synchronize all ESP32 alert lights registered on `node_id` with the
        current unresolved emergency events in `EmergencyDatabase`.
        """
        actuators = self.db.list_actuators_for_node(node_id)
        light_actuators = [
            a for a in actuators if is_actuator_alert_light(a.actuator_type)
        ]
        if not light_actuators:
            return []

        unresolved = self.get_unresolved_alert_events(node_id)
        should_be_on = len(unresolved) > 0
        effective_event_id = unresolved[0].event_id if unresolved else event_id

        results: List[ActuatorDispatchResult] = []
        for act in light_actuators:
            if should_be_on and act.current_state != ActuatorState.ON:
                results.append(
                    await self.dispatch_command(
                        actuator_id=act.actuator_id,
                        command=ActuatorCommandType.LIGHT_ON,
                        control_mode=ActuatorControlMode.PROTECTION_MODE,
                        event_id=effective_event_id,
                        reason=reason or "Unresolved environmental hazard active on node",
                    )
                )
            elif not should_be_on and act.current_state in (
                ActuatorState.ON,
                ActuatorState.UNKNOWN,
            ):
                results.append(
                    await self.dispatch_command(
                        actuator_id=act.actuator_id,
                        command=ActuatorCommandType.LIGHT_OFF,
                        control_mode=ActuatorControlMode.PROTECTION_MODE,
                        event_id=effective_event_id,
                        reason=reason or "All active emergency events resolved; turning alert light OFF",
                    )
                )
        return results

    async def apply_policy_decision(
        self, decision: PolicyDecisionResult
    ) -> List[ActuatorDispatchResult]:
        """
        Translate a Phase 2 `PolicyDecisionResult` into safe actuator commands
        for all actuators bound to `decision.node_id`.
        """
        actuators = self.db.list_actuators_for_node(decision.node_id)
        if not actuators:
            return []

        results: List[ActuatorDispatchResult] = []
        rec = decision.actuator_recommendation
        event_id = decision.active_event_id
        unresolved_alert_events: Optional[List[EmergencyEventResponse]] = None

        for act in actuators:
            if is_actuator_alert_light(act.actuator_type):
                if unresolved_alert_events is None:
                    unresolved_alert_events = self.get_unresolved_alert_events(
                        decision.node_id
                    )

                qualifying_now = is_qualifying_environmental_hazard(
                    decision.evaluation,
                    allow_diagnostic=self.alert_light_on_diagnostic,
                )
                if decision.lifecycle_transition == EventLifecycleTransition.EVENT_RESOLVED:
                    should_be_on = len(unresolved_alert_events) > 0
                else:
                    should_be_on = qualifying_now or (len(unresolved_alert_events) > 0)

                target_event_id = event_id or (
                    unresolved_alert_events[0].event_id
                    if unresolved_alert_events
                    else None
                )

                if should_be_on:
                    if act.current_state != ActuatorState.ON:
                        res = await self.dispatch_command(
                            actuator_id=act.actuator_id,
                            command=ActuatorCommandType.LIGHT_ON,
                            control_mode=ActuatorControlMode.PROTECTION_MODE,
                            event_id=target_event_id,
                            reason=rec.rationale or decision.reason,
                        )
                        results.append(res)
                else:
                    if act.current_state == ActuatorState.ON or (
                        decision.lifecycle_transition
                        == EventLifecycleTransition.EVENT_RESOLVED
                        and act.current_state == ActuatorState.UNKNOWN
                    ):
                        res = await self.dispatch_command(
                            actuator_id=act.actuator_id,
                            command=ActuatorCommandType.LIGHT_OFF,
                            control_mode=ActuatorControlMode.PROTECTION_MODE,
                            event_id=target_event_id,
                            reason="Emergency hazard cleared; turning alert light OFF",
                        )
                        results.append(res)
                continue

            filtration_capable = is_actuator_filtration_capable(act.actuator_type)

            if (
                rec.recommended_action == "ACTIVATE_FILTRATION"
                and filtration_capable
                and not self.demo_mode_enabled
            ):
                res = await self.dispatch_command(
                    actuator_id=act.actuator_id,
                    command=ActuatorCommandType.FAN_ON,
                    control_mode=ActuatorControlMode.PROTECTION_MODE,
                    event_id=event_id,
                    reason=rec.rationale,
                )
                results.append(res)
            elif (
                rec.recommended_action == "ACTIVATE_FILTRATION"
                and not filtration_capable
            ):
                # Never activate unfiltered fan automatically in real protection mode
                res = await self.dispatch_command(
                    actuator_id=act.actuator_id,
                    command=ActuatorCommandType.FAN_ON,
                    control_mode=ActuatorControlMode.PROTECTION_MODE,
                    event_id=event_id,
                    reason=rec.rationale,
                )
                results.append(res)
            elif (
                decision.lifecycle_transition == EventLifecycleTransition.EVENT_RESOLVED
                and act.current_state == ActuatorState.ON
            ):
                res = await self.dispatch_command(
                    actuator_id=act.actuator_id,
                    command=ActuatorCommandType.FAN_OFF,
                    control_mode=ActuatorControlMode.PROTECTION_MODE,
                    event_id=event_id,
                    reason="Emergency event resolved; turning actuator OFF",
                )
                results.append(res)
            elif (
                rec.recommended_action == "DO_NOT_ACTIVATE_ON_GAS_HAZARD"
                and act.current_state == ActuatorState.ON
            ):
                res = await self.dispatch_command(
                    actuator_id=act.actuator_id,
                    command=ActuatorCommandType.FAN_OFF,
                    control_mode=ActuatorControlMode.PROTECTION_MODE,
                    event_id=event_id,
                    reason=rec.rationale,
                )
                results.append(res)

        return results

