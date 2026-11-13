"""
FastAPI REST endpoints & Twilio Webhook handlers for Phase 4
Emergency Notifications & Caregiver Escalation.
"""

from __future__ import annotations

import logging
from html import escape as xml_escape
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import parse_qsl

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.emergency.auth import require_manager_auth
from app.emergency.database import RecordNotFoundError
from app.emergency.notification_provider import (
    build_custom_test_voice_twiml,
    map_twilio_status,
    validate_twilio_signature,
    verify_ack_token,
)
from app.emergency.schemas import (
    EmergencyEventResponse,
    EmergencySeverity,
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

    phone_number: Optional[str] = Field(default=None, min_length=8, max_length=16)
    channel: Literal["SMS", "VOICE_CALL", "BOTH"] = "SMS"
    message: str = Field(
        default="NAVOSEDGE TEST ALERT: This is a simulated/live connectivity verification message.",
        min_length=1,
        max_length=500,
    )

    @field_validator("phone_number")
    @classmethod
    def _validate_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
        return validate_e164_phone(v)


class TestWorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone_number: Optional[str] = Field(default=None, min_length=8, max_length=16)
    secondary_phone_number: Optional[str] = Field(default=None, min_length=8, max_length=16)
    hazard_type: str = Field(
        default="SUDDEN_SMOKE_OR_PARTICULATE_SPIKE",
        min_length=1,
        max_length=64,
    )
    severity: EmergencySeverity = EmergencySeverity.CRITICAL
    pm2_5: Optional[float] = Field(default=185.0, ge=0.0)
    pm10: Optional[float] = Field(default=240.0, ge=0.0)
    gas_status: str = Field(default="POSSIBLE_SMOKE_OR_VOC_SPIKE", max_length=120)
    location: str = Field(default="Test Monitoring Zone", min_length=1, max_length=255)
    custom_message: Optional[str] = Field(default=None, max_length=300)
    dispatch_mode: Optional[Literal["REST", "STUDIO"]] = None
    track_in_db: bool = True

    @field_validator("phone_number", "secondary_phone_number")
    @classmethod
    def _validate_phones(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return None
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
    if (
        getattr(settings, "TWILIO_MODE", "SIMULATED") == "LIVE"
        and getattr(settings, "TWILIO_VALIDATE_WEBHOOK_SIGNATURE", True)
    ):
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


@router.get("/api/v1/notifications/status")
async def get_notification_integration_status(
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    """
    Return non-sensitive runtime status of the Twilio/Simulated notification
    integration (never exposes credentials, tokens, or phone numbers).
    """
    settings = request.app.state.settings
    service = request.app.state.notification_service
    provider = service.provider
    is_sim = bool(getattr(provider, "is_simulated", provider.provider_name == "SIMULATED"))
    verified_list = getattr(settings, "twilio_verified_numbers_list", [])
    return {
        "mode": "SIMULATED" if is_sim else "LIVE",
        "is_simulated": is_sim,
        "provider": provider.provider_name,
        "trial_mode": bool(getattr(provider, "trial_mode", getattr(settings, "TWILIO_TRIAL_MODE", True))),
        "dispatch_mode": getattr(service, "dispatch_mode", "REST"),
        "studio_flow_configured": bool(getattr(settings, "TWILIO_STUDIO_FLOW_SID", None)),
        "credentials_configured": bool(
            getattr(settings, "TWILIO_ACCOUNT_SID", None)
            and getattr(settings, "TWILIO_AUTH_TOKEN", None)
            and getattr(settings, "TWILIO_FROM_NUMBER", None)
        ),
        "webhook_base_configured": bool(getattr(settings, "PUBLIC_WEBHOOK_BASE_URL", None)),
        "webhook_signature_validation": bool(
            getattr(settings, "TWILIO_VALIDATE_WEBHOOK_SIGNATURE", True)
        ),
        "verified_numbers_count": len(verified_list),
        "test_recipient_configured": bool(getattr(settings, "TWILIO_TEST_RECIPIENT", None)),
        "secondary_recipient_configured": bool(
            getattr(settings, "TWILIO_SECONDARY_RECIPIENT", None)
        ),
    }


def _resolve_test_recipient(
    explicit_phone: Optional[str], settings: Any, env_attr: str = "TWILIO_TEST_RECIPIENT"
) -> str:
    candidate = explicit_phone or getattr(settings, env_attr, None)
    if not candidate or not str(candidate).strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"phone_number is required (or configure NAVOS_{env_attr}).",
        )
    try:
        return validate_e164_phone(str(candidate))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.post("/api/v1/notifications/test")
async def send_test_notification(
    payload: TestNotificationRequest,
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    """Send a test SMS, Voice Call, or BOTH using the configured provider (SIMULATED or LIVE)."""
    settings = request.app.state.settings
    service = request.app.state.notification_service
    to_number = _resolve_test_recipient(payload.phone_number, settings, "TWILIO_TEST_RECIPIENT")
    base_url = getattr(service, "public_webhook_base_url", None)
    status_url = f"{base_url}/api/v1/webhooks/twilio/status" if base_url else None
    gather_url = f"{base_url}/api/v1/webhooks/twilio/voice/gather" if base_url else None

    if payload.channel == "SMS":
        result = await service.provider.send_sms(
            to_number=to_number,
            body=payload.message,
            status_callback_url=status_url,
        )
        return {
            **result.model_dump(mode="json"),
            "mode": "SIMULATED" if result.is_simulated else "LIVE",
        }

    twiml = build_custom_test_voice_twiml(
        message=payload.message,
        gather_action_url=gather_url,
    )
    if payload.channel == "VOICE_CALL":
        result = await service.provider.make_voice_call(
            to_number=to_number,
            twiml=twiml,
            status_callback_url=status_url,
        )
        return {
            **result.model_dump(mode="json"),
            "mode": "SIMULATED" if result.is_simulated else "LIVE",
        }

    # BOTH channels cleanly executed
    sms_res = await service.provider.send_sms(
        to_number=to_number,
        body=payload.message,
        status_callback_url=status_url,
    )
    call_res = await service.provider.make_voice_call(
        to_number=to_number,
        twiml=twiml,
        status_callback_url=status_url,
    )
    return {
        "success": sms_res.success and call_res.success,
        "channel": "BOTH",
        "mode": "SIMULATED" if sms_res.is_simulated else "LIVE",
        "is_simulated": sms_res.is_simulated,
        "trial_mode": sms_res.trial_mode,
        "provider": service.provider.provider_name,
        "sms": sms_res.model_dump(mode="json"),
        "voice_call": call_res.model_dump(mode="json"),
    }


@router.post("/api/v1/notifications/test-workflow")
async def trigger_test_notification_workflow(
    payload: TestWorkflowRequest,
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    """
    Trigger a complete end-to-end Twilio verification workflow (SMS + Voice <Gather>
    TwiML + acknowledgement link + callback/escalation readiness) via ONE
    authenticated UNO Q request, without requiring a physical sensor emergency.
    """
    settings = request.app.state.settings
    service = request.app.state.notification_service
    to_number = _resolve_test_recipient(payload.phone_number, settings, "TWILIO_TEST_RECIPIENT")
    secondary_candidate = payload.secondary_phone_number or getattr(
        settings, "TWILIO_SECONDARY_RECIPIENT", None
    )
    secondary_number: Optional[str] = None
    if secondary_candidate and str(secondary_candidate).strip():
        try:
            secondary_number = validate_e164_phone(str(secondary_candidate))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid secondary phone number: {exc}",
            ) from exc

    return await service.dispatch_test_workflow(
        to_number=to_number,
        secondary_number=secondary_number,
        hazard_type=payload.hazard_type,
        severity=payload.severity,
        pm2_5=payload.pm2_5,
        pm10=payload.pm10,
        gas_status=payload.gas_status,
        location=payload.location,
        custom_message=payload.custom_message,
        dispatch_mode=payload.dispatch_mode,
        track_in_db=payload.track_in_db,
    )


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

    twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{xml_escape(reply)}</Message></Response>'
    return Response(content=twiml, media_type="application/xml")


@router.post("/api/v1/webhooks/twilio/voice/gather")
async def twilio_voice_gather_webhook(
    request: Request,
    notification_id: Optional[str] = Query(default=None),
):
    """
    Handle Twilio `<Gather>` DTMF keypad acknowledgement.
    Records every pressed digit response in `event_metadata['dtmf_responses']`.
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

    acknowledged = digits == "1"
    if target_ntf is not None:
        try:
            db.record_event_dtmf_response(
                event_id=target_ntf.event_id,
                notification_id=target_ntf.notification_id,
                digit=digits or "NO_INPUT",
                acknowledged=acknowledged,
                call_sid=call_sid or None,
            )
        except RecordNotFoundError:
            pass

    if acknowledged and target_ntf is not None:
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
    elif digits == "2":
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Say voice=\"alice\">"
            "Your keypad response was recorded as unable to acknowledge. NavosEdge will continue escalating this alert to the next caregiver. Goodbye."
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


@router.post("/api/v1/webhooks/twilio/studio")
async def twilio_studio_callback_webhook(request: Request):
    """
    Handle consolidated status and DTMF callbacks emitted by Twilio Studio Flow
    widgets (`Make Request` / status webhooks), validated via `X-Twilio-Signature`.
    """
    params = await _parse_and_verify_twilio_form(request)
    ntf_id = (params.get("notification_id") or "").strip()
    exec_sid = (
        params.get("ExecutionSid") or params.get("StudioExecutionSid") or ""
    ).strip()
    call_sid = (params.get("CallSid") or "").strip()
    msg_sid = (params.get("MessageSid") or "").strip()
    raw_status = (
        params.get("Status")
        or params.get("ExecutionStatus")
        or params.get("CallStatus")
        or params.get("MessageStatus")
        or ""
    ).strip()
    digits = (params.get("Digits") or "").strip()
    err_note = params.get("ErrorMessage") or params.get("ErrorCode")

    db = request.app.state.emergency_db
    service = request.app.state.notification_service

    target_ntf = None
    if ntf_id:
        target_ntf = db.get_notification(ntf_id)
    if target_ntf is None and exec_sid:
        target_ntf = db.get_notification_by_provider_ref(exec_sid)
    if target_ntf is None and call_sid:
        target_ntf = db.get_notification_by_provider_ref(call_sid)
    if target_ntf is None and msg_sid:
        target_ntf = db.get_notification_by_provider_ref(msg_sid)

    if target_ntf is None:
        return {"status": "ignored", "reason": "Notification record not found"}

    if raw_status:
        mapped_status = map_twilio_status(raw_status)
        target_ntf = db.update_notification_delivery(
            notification_id=target_ntf.notification_id,
            delivery_status=mapped_status,
            failure_reason=str(err_note) if err_note else None,
        )

    studio_meta: Dict[str, Any] = {}
    if exec_sid:
        studio_meta["last_studio_execution_sid"] = exec_sid
    if call_sid:
        studio_meta["last_studio_call_sid"] = call_sid
    if msg_sid:
        studio_meta["last_studio_message_sid"] = msg_sid
    if studio_meta:
        try:
            db.merge_emergency_event_metadata(target_ntf.event_id, studio_meta)
        except RecordNotFoundError:
            pass

    if digits:
        acknowledged = digits == "1"
        try:
            db.record_event_dtmf_response(
                event_id=target_ntf.event_id,
                notification_id=target_ntf.notification_id,
                digit=digits,
                acknowledged=acknowledged,
                call_sid=call_sid or None,
            )
        except RecordNotFoundError:
            pass
        if acknowledged:
            service.record_human_acknowledgement(
                notification_id=target_ntf.notification_id,
                acknowledgement_status=HumanAcknowledgementStatus.ACKNOWLEDGED,
                source="TWILIO_STUDIO_DTMF",
            )
            target_ntf = db.get_notification(target_ntf.notification_id) or target_ntf

    return {
        "status": "updated",
        "notification_id": target_ntf.notification_id,
        "delivery_status": target_ntf.delivery_status.value,
        "acknowledgement_status": target_ntf.acknowledgement_status.value,
        "digits_recorded": digits or None,
    }
