"""
Phase 5 FastAPI routes for Manager Dashboard Emergency Integration:
Overview, Residents, Emergency Contacts, Nodes, Incident Details,
Notification Centre, Retry, Synthetic Demo Simulation, and Emergency SSE.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from starlette.responses import StreamingResponse

from app.emergency.auth import require_manager_auth, require_safety_info_access
from app.emergency.database import (
    DuplicateRecordError,
    EmergencyDatabase,
    ForeignKeyViolationError,
    RecordNotFoundError,
)
from app.emergency.notification_service import _group_contacts_by_escalation_level
from app.emergency.schemas import (
    ActuatorConnectionStatus,
    EmergencyContactCreate,
    EmergencyContactResponse,
    EmergencyContactUpdate,
    EmergencyEventResponse,
    EmergencyEventStatus,
    EmergencySeverity,
    HumanAcknowledgementStatus,
    NodeRegistration,
    NodeResponse,
    NotificationChannel,
    NotificationDeliveryStatus,
    NotificationResponse,
    ResidentCreate,
    ResidentResponse,
    ResidentUpdate,
    utc_now,
)
from app.schemas.inference import InferenceResult, InferenceStatus
from app.schemas.sensor import (
    EnvironmentReading,
    GasSensorReading,
    GasSensors,
    ParticulateMatterReading,
    SensorPayload,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/emergency", tags=["emergency"])


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------


class NodeAssociateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resident_id: Optional[str] = Field(default=None, max_length=64)


class EventActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    notes: Optional[str] = Field(default=None, max_length=500)


class DemoSimulateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    node_id: str = Field(default="node-01", min_length=1, max_length=64)
    pm2_5: float = Field(default=195.0, ge=0.0, le=1000.0)
    pm10: float = Field(default=280.0, ge=0.0, le=1500.0)
    mq2_v: float = Field(default=1.1, ge=0.0, le=5.0)
    mq9_v: float = Field(default=1.0, ge=0.0, le=5.0)
    mq135_v: float = Field(default=1.2, ge=0.0, le=5.0)


# ---------------------------------------------------------------------------
# Overview Computation Helper
# ---------------------------------------------------------------------------


def build_emergency_overview(
    db: EmergencyDatabase, node_registry: Any = None
) -> Dict[str, Any]:
    all_events = db.list_emergency_events()
    unresolved = [
        e
        for e in all_events
        if e.event_status
        not in (EmergencyEventStatus.RESOLVED, EmergencyEventStatus.CANCELLED)
    ]
    resolved_recent = [
        e for e in all_events if e.event_status == EmergencyEventStatus.RESOLVED
    ][:10]

    critical_or_emergency = sum(
        1
        for e in unresolved
        if e.severity in (EmergencySeverity.CRITICAL, EmergencySeverity.EMERGENCY)
    )
    warning_count = sum(
        1
        for e in unresolved
        if e.severity in (EmergencySeverity.WARNING, EmergencySeverity.MEDIUM, EmergencySeverity.HIGH)
    )
    unacknowledged_count = sum(
        1
        for e in unresolved
        if e.event_status
        in (
            EmergencyEventStatus.DETECTED,
            EmergencyEventStatus.ACTIVE_UNACKNOWLEDGED,
            EmergencyEventStatus.ESCALATING,
        )
    )
    escalating_count = sum(
        1
        for e in unresolved
        if e.event_status == EmergencyEventStatus.ESCALATING
        or e.escalation_level > 1
    )

    nodes = db.list_nodes(node_registry=node_registry)
    online_nodes = sum(
        1
        for n in nodes
        if (n.runtime_status == "active")
        or (n.runtime_status is None and n.operational_status.value in ("ONLINE", "ACTIVE"))
    )
    offline_nodes = len(nodes) - online_nodes

    actuators = []
    for n in nodes:
        actuators.extend(db.list_actuators_for_node(n.node_id))
    online_actuators = sum(
        1 for a in actuators if a.connection_status == ActuatorConnectionStatus.ONLINE
    )
    offline_actuators = len(actuators) - online_actuators

    pending_notifications = 0
    for ev in unresolved:
        for ntf in db.list_notifications_for_event(ev.event_id):
            if ntf.acknowledgement_status == HumanAcknowledgementStatus.PENDING:
                pending_notifications += 1

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "active_emergency_count": len(unresolved),
        "critical_emergency_count": critical_or_emergency,
        "warning_count": warning_count,
        "unacknowledged_count": unacknowledged_count,
        "escalation_in_progress_count": escalating_count,
        "recently_resolved_count": len(resolved_recent),
        "online_nodes": online_nodes,
        "offline_nodes": offline_nodes,
        "total_nodes": len(nodes),
        "online_actuators": online_actuators,
        "offline_actuators": offline_actuators,
        "total_actuators": len(actuators),
        "pending_caregiver_notifications": pending_notifications,
    }


# ---------------------------------------------------------------------------
# 1. Overview & Live SSE Stream
# ---------------------------------------------------------------------------


@router.get("/overview")
async def get_emergency_overview(
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    db: EmergencyDatabase = request.app.state.emergency_db
    node_registry = getattr(request.app.state, "node_registry", None)
    return build_emergency_overview(db, node_registry=node_registry)


@router.get("/stream")
async def emergency_sse_stream(request: Request):
    """
    Real-time SSE stream for emergency overview, incidents, actuators, and
    notifications. Supports graceful reconnect and never crashes on disconnect.
    """
    db: EmergencyDatabase = request.app.state.emergency_db
    node_registry = getattr(request.app.state, "node_registry", None)

    async def generator():
        last_signature = ""
        try:
            while True:
                if await request.is_disconnected():
                    break
                overview = build_emergency_overview(db, node_registry=node_registry)
                events = [
                    e.model_dump(mode="json") for e in db.list_emergency_events()[:25]
                ]
                snapshot = {"overview": overview, "events": events}
                sig = json.dumps(snapshot, sort_keys=True)
                if sig != last_signature:
                    last_signature = sig
                    yield f"event: emergency_update\ndata: {sig}\n\n"
                else:
                    yield f"event: heartbeat\ndata: {json.dumps({'time': datetime.now(timezone.utc).isoformat()})}\n\n"
                await asyncio.sleep(2.5)
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# 2. Residents
# ---------------------------------------------------------------------------


@router.get("/residents", response_model=List[ResidentResponse])
async def list_residents(
    request: Request,
    active_only: bool = False,
    include_safety_info: bool = False,
    _operator: str = Depends(require_manager_auth),
):
    if include_safety_info:
        require_safety_info_access(request)
    db: EmergencyDatabase = request.app.state.emergency_db
    return db.list_residents(
        active_only=active_only, include_safety_info=include_safety_info
    )


@router.post(
    "/residents",
    response_model=ResidentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_resident(
    payload: ResidentCreate,
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    db: EmergencyDatabase = request.app.state.emergency_db
    try:
        return db.create_resident(payload, include_safety_info=False)
    except DuplicateRecordError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ForeignKeyViolationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/residents/{resident_id}", response_model=ResidentResponse)
async def get_resident(
    resident_id: str,
    request: Request,
    include_safety_info: bool = False,
    _operator: str = Depends(require_manager_auth),
):
    if include_safety_info:
        require_safety_info_access(request)
    db: EmergencyDatabase = request.app.state.emergency_db
    res = db.get_resident(resident_id, include_safety_info=include_safety_info)
    if res is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resident '{resident_id}' not found",
        )
    return res


@router.patch("/residents/{resident_id}", response_model=ResidentResponse)
async def update_resident(
    resident_id: str,
    payload: ResidentUpdate,
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    db: EmergencyDatabase = request.app.state.emergency_db
    try:
        return db.update_resident(resident_id, payload, include_safety_info=False)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ForeignKeyViolationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/residents/{resident_id}/deactivate", response_model=ResidentResponse)
async def deactivate_resident(
    resident_id: str,
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    db: EmergencyDatabase = request.app.state.emergency_db
    try:
        return db.deactivate_resident(resident_id)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# 3. Emergency Contacts
# ---------------------------------------------------------------------------


@router.get(
    "/residents/{resident_id}/contacts",
    response_model=List[EmergencyContactResponse],
)
async def list_resident_contacts(
    resident_id: str,
    request: Request,
    active_only: bool = False,
    _operator: str = Depends(require_manager_auth),
):
    db: EmergencyDatabase = request.app.state.emergency_db
    if db.get_resident(resident_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resident '{resident_id}' not found",
        )
    return db.list_contacts_for_resident(resident_id, active_only=active_only)


@router.post(
    "/contacts",
    response_model=EmergencyContactResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_contact(
    payload: EmergencyContactCreate,
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    db: EmergencyDatabase = request.app.state.emergency_db
    try:
        return db.create_contact(payload)
    except DuplicateRecordError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ForeignKeyViolationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.patch("/contacts/{contact_id}", response_model=EmergencyContactResponse)
async def update_contact(
    contact_id: str,
    payload: EmergencyContactUpdate,
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    db: EmergencyDatabase = request.app.state.emergency_db
    try:
        return db.update_contact(contact_id, payload)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/contacts/{contact_id}/deactivate", response_model=EmergencyContactResponse)
async def deactivate_contact(
    contact_id: str,
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    db: EmergencyDatabase = request.app.state.emergency_db
    try:
        return db.deactivate_contact(contact_id)
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# 4. Registered Nodes (UNO Q)
# ---------------------------------------------------------------------------


@router.get("/nodes", response_model=List[NodeResponse])
async def list_registered_nodes(
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    db: EmergencyDatabase = request.app.state.emergency_db
    node_registry = getattr(request.app.state, "node_registry", None)
    return db.list_nodes(node_registry=node_registry)


@router.post(
    "/nodes",
    response_model=NodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_emergency_node(
    payload: NodeRegistration,
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    db: EmergencyDatabase = request.app.state.emergency_db
    node_registry = getattr(request.app.state, "node_registry", None)
    try:
        return db.register_node(payload, node_registry=node_registry)
    except DuplicateRecordError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ForeignKeyViolationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/nodes/{node_id}/associate", response_model=NodeResponse)
async def associate_node(
    node_id: str,
    payload: NodeAssociateRequest,
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    db: EmergencyDatabase = request.app.state.emergency_db
    node_registry = getattr(request.app.state, "node_registry", None)
    try:
        return db.associate_node_with_resident(
            node_id, payload.resident_id, node_registry=node_registry
        )
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ForeignKeyViolationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# 5. Emergency Events & Incident Detail
# ---------------------------------------------------------------------------


@router.get("/events", response_model=List[EmergencyEventResponse])
async def list_emergency_events(
    request: Request,
    node_id: Optional[str] = None,
    resident_id: Optional[str] = None,
    event_status: Optional[EmergencyEventStatus] = None,
    _operator: str = Depends(require_manager_auth),
):
    db: EmergencyDatabase = request.app.state.emergency_db
    return db.list_emergency_events(
        node_id=node_id, resident_id=resident_id, event_status=event_status
    )


@router.get("/events/{event_id}")
async def get_emergency_event_detail(
    event_id: str,
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    """
    Full incident detail view combining environmental telemetry, Phase 2 policy
    recommendations, Phase 3 actuator state/commands, Phase 4 notifications,
    escalation hierarchy, and a chronological timeline.
    """
    db: EmergencyDatabase = request.app.state.emergency_db
    event = db.get_emergency_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"EmergencyEvent '{event_id}' not found",
        )

    node = db.get_node(
        event.associated_node_id,
        node_registry=getattr(request.app.state, "node_registry", None),
    )
    resident = (
        db.get_resident(event.resident_id, include_safety_info=False)
        if event.resident_id
        else None
    )
    actuators = db.list_actuators_for_node(event.associated_node_id)
    command_logs = []
    for act in actuators:
        for cmd in db.list_command_logs_for_actuator(act.actuator_id):
            if cmd.event_id == event_id:
                command_logs.append(cmd)

    notifications = db.list_notifications_for_event(event_id)
    contacts = (
        db.list_contacts_for_resident(resident.resident_id, active_only=False)
        if resident is not None
        else []
    )
    contact_map = {c.contact_id: c for c in contacts}
    grouped = _group_contacts_by_escalation_level(
        [c for c in contacts if c.active_status]
    )

    # Build chronological timeline
    timeline: List[Dict[str, Any]] = [
        {
            "timestamp": event.detected_at.isoformat(),
            "category": "EVENT",
            "title": f"Hazard detected: {event.event_type} ({event.severity.value})",
            "detail": event.decision_reason or "Hazard policy triggered",
        }
    ]
    for cmd in command_logs:
        timeline.append(
            {
                "timestamp": cmd.requested_at.isoformat(),
                "category": "ACTUATOR",
                "title": f"Actuator {cmd.actuator_id}: {cmd.command} [{cmd.execution_status.value}]",
                "detail": cmd.error_details or "Dispatched to ESP32",
            }
        )
    for ntf in notifications:
        c = contact_map.get(ntf.contact_id)
        c_label = c.full_name if c else ntf.contact_id
        timeline.append(
            {
                "timestamp": ntf.created_at.isoformat(),
                "category": "NOTIFICATION",
                "title": f"{ntf.notification_channel.value} -> {c_label} [{ntf.delivery_status.value}]",
                "detail": f"Ack: {ntf.acknowledgement_status.value}"
                + (f" ({ntf.failure_reason})" if ntf.failure_reason else ""),
            }
        )
        if ntf.acknowledged_at is not None:
            timeline.append(
                {
                    "timestamp": ntf.acknowledged_at.isoformat(),
                    "category": "ACKNOWLEDGEMENT",
                    "title": f"Human acknowledgement received from {c_label}",
                    "detail": f"Status: {ntf.acknowledgement_status.value}",
                }
            )
    if event.resolved_at is not None:
        timeline.append(
            {
                "timestamp": event.resolved_at.isoformat(),
                "category": "RESOLUTION",
                "title": "Incident manually resolved",
                "detail": f"By: {(event.event_metadata or {}).get('resolved_by', 'operator')}",
            }
        )
    timeline.sort(key=lambda item: item["timestamp"])

    return {
        "event": event.model_dump(mode="json"),
        "node": node.model_dump(mode="json") if node else None,
        "resident": resident.model_dump(mode="json") if resident else None,
        "actuators": [a.model_dump(mode="json") for a in actuators],
        "command_logs": [c.model_dump(mode="json") for c in command_logs],
        "notifications": [
            {
                **n.model_dump(mode="json"),
                "contact_name": contact_map[n.contact_id].full_name
                if n.contact_id in contact_map
                else None,
                "contact_priority": contact_map[n.contact_id].priority
                if n.contact_id in contact_map
                else None,
            }
            for n in notifications
        ],
        "escalation": {
            "current_level": event.escalation_level,
            "all_contacts_exhausted": bool(
                (event.event_metadata or {}).get("all_contacts_exhausted", False)
            ),
            "levels": {
                str(lvl): [
                    {
                        "contact_id": c.contact_id,
                        "full_name": c.full_name,
                        "priority": c.priority,
                        "relationship": c.relationship,
                    }
                    for c in clist
                ]
                for lvl, clist in grouped.items()
            },
        },
        "timeline": timeline,
    }


@router.post("/events/{event_id}/acknowledge", response_model=EmergencyEventResponse)
async def acknowledge_event_by_manager(
    event_id: str,
    request: Request,
    payload: Optional[EventActionRequest] = None,
    operator: str = Depends(require_manager_auth),
):
    db: EmergencyDatabase = request.app.state.emergency_db
    ntf_service = request.app.state.notification_service
    event = db.get_emergency_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"EmergencyEvent '{event_id}' not found",
        )

    now = utc_now()
    # Mark any pending notifications acknowledged if present, else update event directly
    ntfs = db.list_notifications_for_event(event_id)
    pending = [
        n
        for n in ntfs
        if n.acknowledgement_status == HumanAcknowledgementStatus.PENDING
    ]
    if pending:
        ntf_service.record_human_acknowledgement(
            notification_id=pending[0].notification_id,
            acknowledgement_status=HumanAcknowledgementStatus.ACKNOWLEDGED,
            acknowledged_at=now,
            source=f"MANAGER:{operator}",
        )
    meta = dict(event.event_metadata or {})
    meta["acknowledged_by"] = operator
    if payload and payload.notes:
        meta["acknowledgement_notes"] = payload.notes
    return db.update_emergency_event_lifecycle(
        event_id,
        event_status=EmergencyEventStatus.ACKNOWLEDGED,
        acknowledged_at=now,
        event_metadata=meta,
    )


@router.post("/events/{event_id}/resolve", response_model=EmergencyEventResponse)
async def resolve_event_by_manager(
    event_id: str,
    request: Request,
    payload: Optional[EventActionRequest] = None,
    operator: str = Depends(require_manager_auth),
):
    ntf_service = request.app.state.notification_service
    try:
        return ntf_service.resolve_event_manually(
            event_id,
            resolved_by=operator,
            notes=payload.notes if payload else None,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# 6. Notification Centre & Retry
# ---------------------------------------------------------------------------


@router.get("/notifications")
async def list_all_notifications(
    request: Request,
    delivery_status: Optional[NotificationDeliveryStatus] = None,
    acknowledgement_status: Optional[HumanAcknowledgementStatus] = None,
    event_id: Optional[str] = None,
    _operator: str = Depends(require_manager_auth),
):
    db: EmergencyDatabase = request.app.state.emergency_db
    events = (
        [e for e in [db.get_emergency_event(event_id)] if e is not None]
        if event_id
        else db.list_emergency_events()
    )
    results: List[Dict[str, Any]] = []
    for ev in events:
        resident = (
            db.get_resident(ev.resident_id, include_safety_info=False)
            if ev.resident_id
            else None
        )
        contacts = (
            {
                c.contact_id: c
                for c in db.list_contacts_for_resident(
                    ev.resident_id, active_only=False
                )
            }
            if ev.resident_id
            else {}
        )
        for ntf in db.list_notifications_for_event(ev.event_id):
            if delivery_status and ntf.delivery_status != delivery_status:
                continue
            if (
                acknowledgement_status
                and ntf.acknowledgement_status != acknowledgement_status
            ):
                continue
            c = contacts.get(ntf.contact_id)
            results.append(
                {
                    **ntf.model_dump(mode="json"),
                    "resident_name": resident.full_name if resident else None,
                    "recipient_name": c.full_name if c else ntf.contact_id,
                    "escalation_level": ev.escalation_level,
                }
            )
    results.sort(key=lambda r: r["created_at"], reverse=True)
    return results


@router.post(
    "/notifications/{notification_id}/retry",
    response_model=NotificationResponse,
)
async def retry_failed_notification(
    notification_id: str,
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    db: EmergencyDatabase = request.app.state.emergency_db
    ntf_service = request.app.state.notification_service
    ntf = db.get_notification(notification_id)
    if ntf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification '{notification_id}' not found",
        )
    if ntf.delivery_status not in (
        NotificationDeliveryStatus.FAILED,
        NotificationDeliveryStatus.UNDELIVERED,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only FAILED or UNDELIVERED notifications can be retried",
        )
    contact = db.get_contact(ntf.contact_id)
    if contact is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found"
        )
    if ntf.notification_channel == NotificationChannel.SMS:
        res = await ntf_service.provider.send_sms(
            to_number=contact.phone_number,
            body=f"NAVOSEDGE RETRY ALERT (Event {ntf.event_id}): Please check on the resident and reply 1 to acknowledge.",
        )
    else:
        res = await ntf_service.provider.make_voice_call(
            to_number=contact.phone_number,
            twiml='<?xml version="1.0" encoding="UTF-8"?><Response><Say>NavosEdge emergency retry alert. Please check on the resident.</Say></Response>',
        )
    return db.update_notification_delivery(
        notification_id=notification_id,
        delivery_status=res.delivery_status,
        provider_reference_id=res.provider_reference_id,
        sent_at=utc_now() if res.success else None,
        failure_reason=res.failure_reason,
    )


# ---------------------------------------------------------------------------
# 7. Synthetic E2E Demo Simulation (Clearly Labeled Synthetic/Demo)
# ---------------------------------------------------------------------------


@router.post("/demo/simulate-event")
async def simulate_emergency_demo(
    payload: DemoSimulateRequest,
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    """
    Runs a clearly-labeled synthetic pollution event through Phase 2
    `HazardPolicyService`, Phase 3 `ActuatorService`, and Phase 4
    `EmergencyNotificationService`. Never claims real sensor or real SMS.
    """
    policy_service = request.app.state.hazard_policy_service
    actuator_service = request.app.state.actuator_service
    ntf_service = request.app.state.notification_service

    sensor_payload = SensorPayload(
        node_id=payload.node_id,
        timestamp=utc_now(),
        environment=EnvironmentReading(temperature_C=26.0, humidity_pct=48.0),
        particulate_matter=ParticulateMatterReading(
            PM1_0=round(payload.pm2_5 * 0.7, 2),
            PM2_5=payload.pm2_5,
            PM10=payload.pm10,
        ),
        gas_sensors=GasSensors(
            MQ2=GasSensorReading(voltage_V=payload.mq2_v, raw_adc=800),
            MQ9=GasSensorReading(voltage_V=payload.mq9_v, raw_adc=750),
            MQ135=GasSensorReading(voltage_V=payload.mq135_v, raw_adc=820),
        ),
    )
    inference = InferenceResult(
        status=InferenceStatus.SUCCESS,
        gas_class="CleanAir",
        class_confidence=0.92,
        uncertainty=0.08,
    )

    decision = policy_service.evaluate_and_decide(
        payload=sensor_payload, inference=inference
    )
    actuator_results = await actuator_service.apply_policy_decision(decision)

    dispatched_ntfs: List[NotificationResponse] = []
    if decision.active_event_id:
        dispatched_ntfs = await ntf_service.dispatch_for_event(
            decision.active_event_id, escalation_level=1
        )

    return {
        "synthetic_demo": True,
        "provider_mode": ntf_service.provider.provider_name,
        "decision": decision.model_dump(mode="json"),
        "actuator_results": [r.model_dump(mode="json") for r in actuator_results],
        "notifications_dispatched": [n.model_dump(mode="json") for n in dispatched_ntfs],
    }

