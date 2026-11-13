"""
FastAPI REST endpoints & Twilio Webhook handlers for Phase 4
Emergency Notifications & Caregiver Escalation.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.emergency.auth import require_manager_auth
from app.emergency.database import RecordNotFoundError
from app.emergency.notification_provider import (
    map_twilio_status,
    validate_twilio_signature,
    verify_ack_token,
)
from app.emergency.schemas import (
    EmergencyEventResponse,
    HumanAcknowledgementStatus,
    NotificationChannel,
    NotificationResponse,
    validate_e164_phone,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["notifications"])


# ---------------------------------------------------------------------------
# Request / Response Schemas
# ---------------------------------------------------------------------------


class TestNotificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone_number: str = Field(..., min_length=8, max_length=16)
    channel: NotificationChannel = NotificationChannel.SMS
    message: str = Field(
        default="NAVOSEDGE TEST ALERT: This is a simulated/live connectivity verification message.",
        min_length=1,
        max_length=500,
    )

    @field_validator("phone_number")
    @classmethod
    def _validate_phone(cls, v: str) -> str:
        return validate_e164_phone(v)


class AcknowledgeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acknowledgement_status: HumanAcknowledgementStatus = (
        HumanAcknowledgementStatus.ACKNOWLEDGED
    )
    source: str = Field(default="DASHBOARD_API", min_length=1, max_length=64)


class ResolveEventRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved_by: str = Field(default="operator", min_length=1, max_length=120)
    notes: Optional[str] = Field(default=None, max_length=500)


# ---------------------------------------------------------------------------
# Helper: Twilio Signature Validation in LIVE mode
# ---------------------------------------------------------------------------


async def _parse_and_verify_twilio_form(request: Request) -> Dict[str, str]:
    raw_body = (await request.body()).decode("utf-8", errors="replace")
    params: Dict[str, str] = dict(parse_qsl(raw_body, keep_blank_values=True))

    settings = request.app.state.settings
    if getattr(settings, "TWILIO_MODE", "SIMULATED") == "LIVE":
        auth_token = getattr(settings, "TWILIO_AUTH_TOKEN", None) or ""
        sig = request.headers.get("X-Twilio-Signature")
        base_url = getattr(settings, "PUBLIC_WEBHOOK_BASE_URL", None)
        if base_url:
            path_q = request.url.path
            if request.url.query:
                path_q = f"{path_q}?{request.url.query}"
            target_url = f"{base_url.rstrip('/')}{path_q}"
        else:
            target_url = str(request.url)

        if not validate_twilio_signature(
            auth_token=auth_token,
            url=target_url,
            params=params,
            signature_header=sig,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid Twilio webhook signature",
            )
    return params


# ---------------------------------------------------------------------------
# Notification & Incident Management Endpoints
# ---------------------------------------------------------------------------


@router.post("/api/v1/notifications/test")
async def send_test_notification(
    payload: TestNotificationRequest,
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    """Send a test SMS or voice call using the configured provider (SIMULATED or LIVE)."""
    service = request.app.state.notification_service
    if payload.channel == NotificationChannel.SMS:
        result = await service.provider.send_sms(
            to_number=payload.phone_number,
            body=payload.message,
        )
    else:
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f"<Response><Say voice=\"alice\">{payload.message}</Say></Response>"
        )
        result = await service.provider.make_voice_call(
            to_number=payload.phone_number,
            twiml=twiml,
        )
    return result.model_dump(mode="json")


@router.post(
    "/api/v1/notifications/events/{event_id}/dispatch",
    response_model=List[NotificationResponse],
)
async def dispatch_event_notifications(
    event_id: str,
    request: Request,
    escalation_level: Optional[int] = Query(default=None, ge=1, le=3),
    _operator: str = Depends(require_manager_auth),
):
    """Manually trigger or retry notification dispatch for an emergency event."""
    service = request.app.state.notification_service
    try:
        return await service.dispatch_for_event(
            event_id, escalation_level=escalation_level
        )
    except RecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.get(
    "/api/v1/notifications/events/{event_id}",
    response_model=List[NotificationResponse],
)
async def list_event_notifications(event_id: str, request: Request):
    """Read notification history and delivery statuses for an emergency event."""
    db = request.app.state.emergency_db
    event = db.get_emergency_event(event_id)
    if event is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"EmergencyEvent '{event_id}' not found",
        )
    return db.list_notifications_for_event(event_id)


@router.get("/api/v1/notifications/ack/{token}")
async def acknowledge_via_signed_link(token: str, request: Request):
    """
    Acknowledge an emergency notification via an HMAC-signed link.
    Contains no PII in the URL.
    """
    service = request.app.state.notification_service
    verified = verify_ack_token(secret=service.ack_signing_secret, token=token)
    if verified is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired acknowledgement token",
        )

    try:
        updated = service.record_human_acknowledgement(
            notification_id=verified["notification_id"],
            acknowledgement_status=HumanAcknowledgementStatus.ACKNOWLEDGED,
            source="SIGNED_LINK",
        )
    except RecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    return {
        "status": "acknowledged",
        "event_id": updated.event_id,
        "notification_id": updated.notification_id,
        "acknowledgement_status": updated.acknowledgement_status.value,
    }


@router.get(
    "/api/v1/notifications/{notification_id}",
    response_model=NotificationResponse,
)
async def get_notification_status(notification_id: str, request: Request):
    """Read delivery and human acknowledgement status for a single notification."""
    db = request.app.state.emergency_db
    ntf = db.get_notification(notification_id)
    if ntf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Notification '{notification_id}' not found",
        )
    return ntf


@router.post(
    "/api/v1/notifications/{notification_id}/acknowledge",
    response_model=NotificationResponse,
)
async def acknowledge_notification(
    notification_id: str,
    payload: AcknowledgeRequest,
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    """Record explicit human acknowledgement for a notification."""
    service = request.app.state.notification_service
    try:
        return service.record_human_acknowledgement(
            notification_id=notification_id,
            acknowledgement_status=payload.acknowledgement_status,
            source=payload.source,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc


@router.post(
    "/api/v1/events/{event_id}/resolve",
    response_model=EmergencyEventResponse,
)
async def resolve_emergency_event(
    event_id: str,
    payload: ResolveEventRequest,
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    """Manually resolve an emergency incident."""
    service = request.app.state.notification_service
    try:
        resolved = service.resolve_event_manually(
            event_id, resolved_by=payload.resolved_by, notes=payload.notes
        )
    except RecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    actuator_service = getattr(request.app.state, "actuator_service", None)
    if actuator_service is not None:
        try:
            await actuator_service.sync_light_for_node(
                resolved.associated_node_id,
                event_id=resolved.event_id,
                reason=f"Emergency event '{resolved.event_id}' manually resolved",
            )
        except Exception as exc:
            logger.warning(
                "Failed to sync alert light after resolving event %s: %s",
                resolved.event_id,
                exc,
            )
    return resolved


# ---------------------------------------------------------------------------
# Twilio Webhooks
# ---------------------------------------------------------------------------


@router.post("/api/v1/webhooks/twilio/sms")
async def twilio_incoming_sms_webhook(request: Request):
    """
    Handle incoming SMS replies from caregivers (e.g. '1', 'ACK', 'OK').
    """
    params = await _parse_and_verify_twilio_form(request)
    from_number = params.get("From", "").strip()
    body = params.get("Body", "").strip().upper()

    db = request.app.state.emergency_db
    service = request.app.state.notification_service

    ack_keywords = {"1", "ACK", "ACKNOWLEDGE", "OK", "YES", "CHECKED"}
    ntf = db.get_latest_pending_notification_for_phone(from_number) if from_number else None

    if ntf is not None and any(body == kw or body.startswith(f"{kw} ") for kw in ack_keywords):
        service.record_human_acknowledgement(
            notification_id=ntf.notification_id,
            acknowledgement_status=HumanAcknowledgementStatus.ACKNOWLEDGED,
            source="TWILIO_SMS_REPLY",
        )
        reply = "NavosEdge: Thank you. Your acknowledgement has been recorded and escalation stopped."
    elif ntf is None:
        reply = "NavosEdge: No active unacknowledged alert found for this number."
    else:
        reply = "NavosEdge: Reply 1 or ACK to confirm you will check on the resident."

    twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{reply}</Message></Response>'
    return Response(content=twiml, media_type="application/xml")


@router.post("/api/v1/webhooks/twilio/voice/gather")
async def twilio_voice_gather_webhook(
    request: Request,
    notification_id: Optional[str] = Query(default=None),
):
    """
    Handle Twilio `<Gather>` DTMF keypad acknowledgement.
    Pressing '1' records explicit human acknowledgement; other digits or silence do not.
    """
    params = await _parse_and_verify_twilio_form(request)
    digits = params.get("Digits", "").strip()
    call_sid = params.get("CallSid", "").strip()

    db = request.app.state.emergency_db
    service = request.app.state.notification_service

    target_ntf = None
    if notification_id:
        target_ntf = db.get_notification(notification_id)
    elif call_sid:
        target_ntf = db.get_notification_by_provider_ref(call_sid)

    if digits == "1" and target_ntf is not None:
        service.record_human_acknowledgement(
            notification_id=target_ntf.notification_id,
            acknowledgement_status=HumanAcknowledgementStatus.ACKNOWLEDGED,
            source="TWILIO_VOICE_DTMF",
        )
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Say voice=\"alice\">"
            "Thank you. Your acknowledgement has been recorded. Escalation has been stopped. Goodbye."
            "</Say></Response>"
        )
    else:
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Say voice=\"alice\">"
            "Acknowledgement was not confirmed. NavosEdge will continue escalating this alert. Goodbye."
            "</Say></Response>"
        )
    return Response(content=twiml, media_type="application/xml")


@router.post("/api/v1/webhooks/twilio/status")
async def twilio_delivery_status_webhook(request: Request):
    """
    Handle Twilio SMS & Voice delivery status callbacks.
    Updates `delivery_status` ONLY — never marks a completed call or voicemail
    pickup (`AnsweredBy=machine_*`) as human acknowledgement.
    """
    params = await _parse_and_verify_twilio_form(request)
    ref_sid = (params.get("MessageSid") or params.get("CallSid") or "").strip()
    raw_status = (params.get("MessageStatus") or params.get("CallStatus") or "").strip()
    answered_by = params.get("AnsweredBy", "").strip().lower()
    err_msg = params.get("ErrorMessage") or params.get("ErrorCode")

    if not ref_sid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing MessageSid or CallSid",
        )

    db = request.app.state.emergency_db
    ntf = db.get_notification_by_provider_ref(ref_sid)
    if ntf is None:
        return {"status": "ignored", "reason": "Unknown provider_reference_id"}

    mapped_status = map_twilio_status(raw_status)
    failure_note = str(err_msg) if err_msg else None
    if answered_by.startswith("machine"):
        failure_note = (
            f"Voicemail detected (AnsweredBy={answered_by}); not acknowledged by human"
        )

    updated = db.update_notification_delivery(
        notification_id=ntf.notification_id,
        delivery_status=mapped_status,
        failure_reason=failure_note,
    )
    return {
        "status": "updated",
        "notification_id": updated.notification_id,
        "delivery_status": updated.delivery_status.value,
        "acknowledgement_status": updated.acknowledgement_status.value,
    }
