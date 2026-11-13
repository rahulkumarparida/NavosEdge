"""
Phase 4: Notification Providers (Twilio LIVE & SIMULATED), TwiML Builders,
Webhook Signature Validation, and Signed Acknowledgement Links.

Credentials are read exclusively from environment-backed Settings and are
never exposed in API responses, logs, reports, or source files.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from html import escape as xml_escape
from typing import Any, Dict, List, Mapping, Optional

import httpx
from pydantic import BaseModel

from app.emergency.schemas import NotificationDeliveryStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider Dispatch Result & Interface
# ---------------------------------------------------------------------------


class NotificationDispatchResult(BaseModel):
    """Structured result returned by `NotificationProvider` implementations."""

    success: bool
    provider: str
    provider_reference_id: Optional[str] = None
    delivery_status: NotificationDeliveryStatus
    failure_reason: Optional[str] = None


class NotificationProvider(ABC):
    """Abstract async provider for SMS and automated voice call dispatch."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifier stored in `emergency_notifications.provider`."""

    @abstractmethod
    async def send_sms(
        self,
        to_number: str,
        body: str,
        status_callback_url: Optional[str] = None,
    ) -> NotificationDispatchResult:
        """Dispatch an SMS alert to an E.164 recipient."""

    @abstractmethod
    async def make_voice_call(
        self,
        to_number: str,
        twiml: str,
        status_callback_url: Optional[str] = None,
    ) -> NotificationDispatchResult:
        """Initiate an automated voice call with inline TwiML."""


# ---------------------------------------------------------------------------
# Simulated Notification Provider (Default Safe Mode)
# ---------------------------------------------------------------------------


@dataclass
class SimulatedMessageRecord:
    reference_id: str
    to_number: str
    body: str
    status_callback_url: Optional[str] = None


@dataclass
class SimulatedCallRecord:
    reference_id: str
    to_number: str
    twiml: str
    status_callback_url: Optional[str] = None


class SimulatedNotificationProvider(NotificationProvider):
    """
    Zero-cost, offline-safe simulated notification provider.
    Never sends real SMS or voice calls and requires no Twilio credentials.
    """

    def __init__(
        self,
        *,
        simulate_failure: bool = False,
        failure_reason: str = "Simulated provider failure",
    ) -> None:
        self.simulate_failure = simulate_failure
        self.failure_reason = failure_reason
        self.dispatched_messages: List[SimulatedMessageRecord] = []
        self.dispatched_calls: List[SimulatedCallRecord] = []

    @property
    def provider_name(self) -> str:
        return "SIMULATED"

    async def send_sms(
        self,
        to_number: str,
        body: str,
        status_callback_url: Optional[str] = None,
    ) -> NotificationDispatchResult:
        if self.simulate_failure:
            return NotificationDispatchResult(
                success=False,
                provider=self.provider_name,
                delivery_status=NotificationDeliveryStatus.FAILED,
                failure_reason=self.failure_reason,
            )

        ref_id = f"sim-sms-{uuid.uuid4().hex[:12]}"
        self.dispatched_messages.append(
            SimulatedMessageRecord(
                reference_id=ref_id,
                to_number=to_number,
                body=body,
                status_callback_url=status_callback_url,
            )
        )
        return NotificationDispatchResult(
            success=True,
            provider=self.provider_name,
            provider_reference_id=ref_id,
            delivery_status=NotificationDeliveryStatus.SENT,
        )

    async def make_voice_call(
        self,
        to_number: str,
        twiml: str,
        status_callback_url: Optional[str] = None,
    ) -> NotificationDispatchResult:
        if self.simulate_failure:
            return NotificationDispatchResult(
                success=False,
                provider=self.provider_name,
                delivery_status=NotificationDeliveryStatus.FAILED,
                failure_reason=self.failure_reason,
            )

        ref_id = f"sim-call-{uuid.uuid4().hex[:12]}"
        self.dispatched_calls.append(
            SimulatedCallRecord(
                reference_id=ref_id,
                to_number=to_number,
                twiml=twiml,
                status_callback_url=status_callback_url,
            )
        )
        return NotificationDispatchResult(
            success=True,
            provider=self.provider_name,
            provider_reference_id=ref_id,
            delivery_status=NotificationDeliveryStatus.RINGING,
        )


# ---------------------------------------------------------------------------
# Twilio LIVE Notification Provider
# ---------------------------------------------------------------------------


class TwilioNotificationProvider(NotificationProvider):
    """
    Asynchronous Twilio REST API client using `httpx.AsyncClient`.
    Never blocks FastAPI event loop or sensor ingestion.
    """

    BASE_URL = "https://api.twilio.com/2010-04-01"

    def __init__(
        self,
        *,
        account_sid: Optional[str],
        auth_token: Optional[str],
        from_number: Optional[str],
        timeout_s: float = 10.0,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._account_sid = (account_sid or "").strip()
        self._auth_token = (auth_token or "").strip()
        self._from_number = (from_number or "").strip()
        self._timeout_s = timeout_s
        self._http_client = http_client

    @property
    def provider_name(self) -> str:
        return "TWILIO"

    def _validate_credentials(self) -> Optional[str]:
        if not self._account_sid or not self._auth_token or not self._from_number:
            return "Missing Twilio credentials (NAVOS_TWILIO_ACCOUNT_SID, NAVOS_TWILIO_AUTH_TOKEN, or NAVOS_TWILIO_FROM_NUMBER)"
        if not self._account_sid.startswith("AC") or len(self._account_sid) < 10:
            return "Invalid Twilio Account SID format"
        return None

    async def _post_form(
        self, endpoint: str, data: Dict[str, str]
    ) -> NotificationDispatchResult:
        cred_err = self._validate_credentials()
        if cred_err is not None:
            logger.warning("Twilio dispatch aborted: %s", cred_err)
            return NotificationDispatchResult(
                success=False,
                provider=self.provider_name,
                delivery_status=NotificationDeliveryStatus.FAILED,
                failure_reason=cred_err,
            )

        url = f"{self.BASE_URL}/Accounts/{self._account_sid}/{endpoint}"
        try:
            if self._http_client is not None:
                resp = await self._http_client.post(
                    url,
                    data=data,
                    auth=(self._account_sid, self._auth_token),
                    timeout=self._timeout_s,
                )
            else:
                async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                    resp = await client.post(
                        url,
                        data=data,
                        auth=(self._account_sid, self._auth_token),
                    )
        except httpx.TimeoutException:
            return NotificationDispatchResult(
                success=False,
                provider=self.provider_name,
                delivery_status=NotificationDeliveryStatus.FAILED,
                failure_reason=f"Twilio API request timed out after {self._timeout_s}s",
            )
        except httpx.RequestError as exc:
            return NotificationDispatchResult(
                success=False,
                provider=self.provider_name,
                delivery_status=NotificationDeliveryStatus.FAILED,
                failure_reason=f"Twilio network error: {type(exc).__name__}",
            )

        if resp.status_code in (401, 403):
            return NotificationDispatchResult(
                success=False,
                provider=self.provider_name,
                delivery_status=NotificationDeliveryStatus.FAILED,
                failure_reason=f"Twilio authentication failed (HTTP {resp.status_code})",
            )

        if resp.status_code >= 400:
            err_detail = f"Twilio API error HTTP {resp.status_code}"
            try:
                err_json = resp.json()
                if isinstance(err_json, dict) and err_json.get("message"):
                    err_detail = f"Twilio HTTP {resp.status_code}: {err_json['message']}"
            except Exception:
                pass
            return NotificationDispatchResult(
                success=False,
                provider=self.provider_name,
                delivery_status=NotificationDeliveryStatus.FAILED,
                failure_reason=err_detail[:500],
            )

        try:
            payload = resp.json()
            sid = payload.get("sid")
            twilio_status = str(payload.get("status", "queued")).lower()
            mapped = map_twilio_status(twilio_status)
            return NotificationDispatchResult(
                success=True,
                provider=self.provider_name,
                provider_reference_id=sid,
                delivery_status=mapped,
            )
        except Exception:
            return NotificationDispatchResult(
                success=False,
                provider=self.provider_name,
                delivery_status=NotificationDeliveryStatus.FAILED,
                failure_reason="Invalid JSON response from Twilio API",
            )

    async def send_sms(
        self,
        to_number: str,
        body: str,
        status_callback_url: Optional[str] = None,
    ) -> NotificationDispatchResult:
        form: Dict[str, str] = {
            "To": to_number,
            "From": self._from_number,
            "Body": body,
        }
        if status_callback_url:
            form["StatusCallback"] = status_callback_url
        return await self._post_form("Messages.json", form)

    async def make_voice_call(
        self,
        to_number: str,
        twiml: str,
        status_callback_url: Optional[str] = None,
    ) -> NotificationDispatchResult:
        form: Dict[str, str] = {
            "To": to_number,
            "From": self._from_number,
            "Twiml": twiml,
            "MachineDetection": "Enable",
        }
        if status_callback_url:
            form["StatusCallback"] = status_callback_url
            form["StatusCallbackEvent"] = "completed"
        result = await self._post_form("Calls.json", form)
        if (
            not result.success
            and result.failure_reason
            and ("trial" in result.failure_reason.lower() or "disallowed parameters" in result.failure_reason.lower())
        ):
            logger.info("Twilio rejected MachineDetection on trial account; retrying voice call without MachineDetection.")
            form.pop("MachineDetection", None)
            result = await self._post_form("Calls.json", form)
        return result


def map_twilio_status(twilio_status: str) -> NotificationDeliveryStatus:
    """Map Twilio MessageStatus / CallStatus strings to `NotificationDeliveryStatus`."""
    normalized = (twilio_status or "").strip().lower()
    mapping = {
        "queued": NotificationDeliveryStatus.QUEUED,
        "accepted": NotificationDeliveryStatus.ACCEPTED,
        "sending": NotificationDeliveryStatus.REQUESTED,
        "sent": NotificationDeliveryStatus.SENT,
        "ringing": NotificationDeliveryStatus.RINGING,
        "in-progress": NotificationDeliveryStatus.IN_PROGRESS,
        "delivered": NotificationDeliveryStatus.DELIVERED,
        "completed": NotificationDeliveryStatus.COMPLETED,
        "undelivered": NotificationDeliveryStatus.UNDELIVERED,
        "busy": NotificationDeliveryStatus.BUSY,
        "no-answer": NotificationDeliveryStatus.NO_ANSWER,
        "canceled": NotificationDeliveryStatus.FAILED,
        "failed": NotificationDeliveryStatus.FAILED,
    }
    return mapping.get(normalized, NotificationDeliveryStatus.FAILED)


# ---------------------------------------------------------------------------
# Webhook Signature Validation & Signed Acknowledgement Tokens
# ---------------------------------------------------------------------------


def validate_twilio_signature(
    *,
    auth_token: str,
    url: str,
    params: Mapping[str, Any],
    signature_header: Optional[str],
) -> bool:
    """
    Validate Twilio `X-Twilio-Signature` HMAC-SHA1 header per Twilio security spec.
    """
    if not auth_token or not signature_header:
        return False

    data = url
    for key in sorted(params.keys()):
        data += f"{key}{params[key]}"

    digest = hmac.new(
        auth_token.encode("utf-8"),
        data.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature_header.strip())


def create_ack_token(
    *,
    secret: str,
    event_id: str,
    notification_id: str,
    ttl_seconds: int = 86400,
    now_ts: Optional[int] = None,
) -> str:
    """
    Create an HMAC-SHA256 signed acknowledgement token containing NO PII.
    Format: `<event_id>.<notification_id>.<exp>.<hex_sig>`
    """
    exp = (now_ts if now_ts is not None else int(time.time())) + ttl_seconds
    payload = f"{event_id}.{notification_id}.{exp}"
    sig = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    return f"{payload}.{sig}"


def verify_ack_token(
    *,
    secret: str,
    token: str,
    now_ts: Optional[int] = None,
) -> Optional[Dict[str, str]]:
    """
    Verify an HMAC-SHA256 signed acknowledgement token.
    Returns `{"event_id": ..., "notification_id": ...}` if valid and unexpired.
    """
    parts = (token or "").split(".")
    if len(parts) != 4:
        return None
    event_id, notification_id, exp_str, provided_sig = parts
    try:
        exp = int(exp_str)
    except ValueError:
        return None

    current = now_ts if now_ts is not None else int(time.time())
    if current > exp:
        return None

    payload = f"{event_id}.{notification_id}.{exp}"
    expected_sig = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:32]
    if not hmac.compare_digest(expected_sig, provided_sig):
        return None
    return {"event_id": event_id, "notification_id": notification_id}


# ---------------------------------------------------------------------------
# SMS & TwiML Formatters
# ---------------------------------------------------------------------------


def format_emergency_sms(
    *,
    hazard_classification: str,
    severity: str,
    pm25: Optional[float],
    pm10: Optional[float],
    gas_status: str,
    system_response: str,
    event_id: str,
    location: Optional[str] = None,
    detected_at_str: Optional[str] = None,
    ack_url: Optional[str] = None,
) -> str:
    """
    Format concise emergency SMS without exposing unnecessary health data.
    Never claims the air was purified by an unfiltered fan.
    """
    pm25_str = f"{pm25:.1f} ug/m3" if pm25 is not None else "Unavailable"
    pm10_str = f"{pm10:.1f} ug/m3" if pm10 is not None else "Unavailable"

    lines = [
        "NAVOSEDGE EMERGENCY ALERT",
        "",
        "A critical environmental condition has been detected at the registered residence.",
    ]
    if location:
        lines.append(f"Location: {location}")
    if detected_at_str:
        lines.append(f"Detected: {detected_at_str}")
    lines.extend(
        [
            "",
            f"Hazard: {hazard_classification}",
            f"Severity: {severity}",
            f"PM2.5: {pm25_str}",
            f"PM10: {pm10_str}",
            f"Gas status: {gas_status}",
            "",
            "System response:",
            system_response,
            "",
            "Please contact the resident and check their safety.",
            "",
            f"Event ID: {event_id}",
            "Reply 1 to acknowledge.",
        ]
    )
    if ack_url:
        lines.append(f"Acknowledge link: {ack_url}")
    lines.append("")
    lines.append("This is an automated safety-support alert.")
    return "\n".join(lines)


def build_voice_twiml(
    *,
    hazard_classification: str,
    severity: str,
    system_response: str,
    gather_action_url: Optional[str] = None,
    location: Optional[str] = None,
) -> str:
    """
    Generate Twilio `<Response><Gather>` TwiML for automated caregiver voice calls.
    """
    loc_phrase = f" at {xml_escape(location)}" if location else ""
    hazard_phrase = xml_escape(hazard_classification.replace("_", " ").lower())
    sev_phrase = xml_escape(severity)
    resp_phrase = xml_escape(system_response)

    action_attr = (
        f' action="{xml_escape(gather_action_url)}" method="POST"'
        if gather_action_url
        else ""
    )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Gather numDigits="1" timeout="10"{action_attr}>'
        "<Say voice=\"alice\">"
        f"Hello, this is NavosEdge automated emergency alert. "
        f"A {sev_phrase} environmental emergency has been detected{loc_phrase}. "
        f"Hazard detected: {hazard_phrase}. "
        f"Confirmed system response: {resp_phrase}. "
        "Please press 1 on your keypad to acknowledge that you received this alert "
        "and will check on the resident."
        "</Say>"
        "</Gather>"
        "<Say voice=\"alice\">"
        "No acknowledgement was received. NavosEdge will continue escalating this alert. Goodbye."
        "</Say>"
        "</Response>"
    )

