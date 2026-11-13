"""
Phase 4: Notification Providers (Twilio LIVE & SIMULATED), TwiML Builders,
Webhook Signature Validation, and Signed Acknowledgement Links.

Credentials are read exclusively from environment-backed Settings and are
never exposed in API responses, logs, reports, or source files.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from html import escape as xml_escape
from typing import Any, Dict, List, Mapping, Optional, Sequence

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
    is_simulated: bool = False
    trial_mode: bool = False
    dispatch_mode: str = "REST"
    attempts: int = 1


class NotificationProvider(ABC):
    """Abstract async provider for SMS, voice call, and Studio workflow dispatch."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identifier stored in `emergency_notifications.provider`."""

    @property
    def is_simulated(self) -> bool:
        """Return True when the provider does not contact live external telephony."""
        return False

    @property
    def trial_mode(self) -> bool:
        """Return True when free-tier Twilio Trial compatibility guardrails are enabled."""
        return False

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

    async def trigger_studio_workflow(
        self,
        to_number: str,
        parameters: Dict[str, Any],
        flow_sid: Optional[str] = None,
    ) -> NotificationDispatchResult:
        """
        Trigger a unified Twilio Studio Flow Execution (1 authenticated API request).
        Default implementation reports unsupported for custom legacy mock subclasses.
        """
        return NotificationDispatchResult(
            success=False,
            provider=self.provider_name,
            delivery_status=NotificationDeliveryStatus.FAILED,
            failure_reason="Twilio Studio workflow dispatch is not supported by this provider.",
            is_simulated=self.is_simulated,
            trial_mode=self.trial_mode,
            dispatch_mode="STUDIO",
        )


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


@dataclass
class SimulatedStudioExecutionRecord:
    reference_id: str
    to_number: str
    flow_sid: str
    parameters: Dict[str, Any] = field(default_factory=dict)


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
        trial_mode: bool = True,
    ) -> None:
        self.simulate_failure = simulate_failure
        self.failure_reason = failure_reason
        self._trial_mode = bool(trial_mode)
        self.dispatched_messages: List[SimulatedMessageRecord] = []
        self.dispatched_calls: List[SimulatedCallRecord] = []
        self.dispatched_studio_executions: List[SimulatedStudioExecutionRecord] = []

    @property
    def provider_name(self) -> str:
        return "SIMULATED"

    @property
    def is_simulated(self) -> bool:
        return True

    @property
    def trial_mode(self) -> bool:
        return self._trial_mode

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
                is_simulated=True,
                trial_mode=self._trial_mode,
                dispatch_mode="REST",
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
            is_simulated=True,
            trial_mode=self._trial_mode,
            dispatch_mode="REST",
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
                is_simulated=True,
                trial_mode=self._trial_mode,
                dispatch_mode="REST",
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
            is_simulated=True,
            trial_mode=self._trial_mode,
            dispatch_mode="REST",
        )

    async def trigger_studio_workflow(
        self,
        to_number: str,
        parameters: Dict[str, Any],
        flow_sid: Optional[str] = None,
    ) -> NotificationDispatchResult:
        if self.simulate_failure:
            return NotificationDispatchResult(
                success=False,
                provider=self.provider_name,
                delivery_status=NotificationDeliveryStatus.FAILED,
                failure_reason=self.failure_reason,
                is_simulated=True,
                trial_mode=self._trial_mode,
                dispatch_mode="STUDIO",
            )

        ref_id = f"sim-studio-{uuid.uuid4().hex[:12]}"
        self.dispatched_studio_executions.append(
            SimulatedStudioExecutionRecord(
                reference_id=ref_id,
                to_number=to_number,
                flow_sid=(flow_sid or "FW_SIMULATED_FLOW"),
                parameters=dict(parameters),
            )
        )
        return NotificationDispatchResult(
            success=True,
            provider=self.provider_name,
            provider_reference_id=ref_id,
            delivery_status=NotificationDeliveryStatus.IN_PROGRESS,
            is_simulated=True,
            trial_mode=self._trial_mode,
            dispatch_mode="STUDIO",
        )


# ---------------------------------------------------------------------------
# Twilio LIVE Notification Provider
# ---------------------------------------------------------------------------


class TwilioNotificationProvider(NotificationProvider):
    """
    Asynchronous Twilio REST & Studio API client using `httpx.AsyncClient`.
    Implements bounded transient retries and never blocks sensor ingestion.
    """

    BASE_URL = "https://api.twilio.com/2010-04-01"
    STUDIO_URL = "https://studio.twilio.com/v2"
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
    TRIAL_UNVERIFIED_ERROR_CODES = {21219, 21608}

    def __init__(
        self,
        *,
        account_sid: Optional[str],
        auth_token: Optional[str],
        from_number: Optional[str],
        timeout_s: float = 10.0,
        http_client: Optional[httpx.AsyncClient] = None,
        max_retries: int = 2,
        retry_backoff_s: float = 0.25,
        trial_mode: bool = False,
        verified_numbers: Optional[Sequence[str]] = None,
        studio_flow_sid: Optional[str] = None,
    ) -> None:
        self._account_sid = (account_sid or "").strip()
        self._auth_token = (auth_token or "").strip()
        self._from_number = (from_number or "").strip()
        self._timeout_s = timeout_s
        self._http_client = http_client
        self._max_retries = max(0, int(max_retries))
        self._retry_backoff_s = max(0.0, float(retry_backoff_s))
        self._trial_mode = bool(trial_mode)
        self._verified_numbers = {
            str(n).strip() for n in (verified_numbers or []) if n and str(n).strip()
        }
        self._studio_flow_sid = (studio_flow_sid or "").strip() or None

    @property
    def provider_name(self) -> str:
        return "TWILIO"

    @property
    def is_simulated(self) -> bool:
        return False

    @property
    def trial_mode(self) -> bool:
        return self._trial_mode

    def _validate_credentials(self) -> Optional[str]:
        if not self._account_sid or not self._auth_token or not self._from_number:
            return "Missing Twilio credentials (NAVOS_TWILIO_ACCOUNT_SID, NAVOS_TWILIO_AUTH_TOKEN, or NAVOS_TWILIO_FROM_NUMBER)"
        if not self._account_sid.startswith("AC") or len(self._account_sid) < 10:
            return "Invalid Twilio Account SID format"
        return None

    def _check_trial_recipient(
        self, to_number: str, *, dispatch_mode: str = "REST"
    ) -> Optional[NotificationDispatchResult]:
        if not self._trial_mode or not self._verified_numbers:
            return None
        normalized = (to_number or "").strip()
        if normalized in self._verified_numbers:
            return None
        return NotificationDispatchResult(
            success=False,
            provider=self.provider_name,
            delivery_status=NotificationDeliveryStatus.FAILED,
            failure_reason=(
                f"Twilio Trial restriction: recipient {normalized} is not in "
                "NAVOS_TWILIO_VERIFIED_NUMBERS. Verify the recipient number in Twilio Console first."
            ),
            is_simulated=False,
            trial_mode=True,
            dispatch_mode=dispatch_mode,
            attempts=1,
        )

    def _retry_delay(self, attempt: int, retry_after_header: Optional[str] = None) -> float:
        if retry_after_header:
            try:
                parsed = float(retry_after_header)
                if parsed > 0:
                    return min(parsed, 2.0)
            except (TypeError, ValueError):
                pass
        return self._retry_backoff_s * (2 ** (attempt - 1))

    async def _post_once(self, url: str, data: Dict[str, str]) -> httpx.Response:
        if self._http_client is not None:
            return await self._http_client.post(
                url,
                data=data,
                auth=(self._account_sid, self._auth_token),
                timeout=self._timeout_s,
            )
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            return await client.post(
                url,
                data=data,
                auth=(self._account_sid, self._auth_token),
            )

    def _format_twilio_http_error(self, resp: httpx.Response) -> str:
        err_detail = f"Twilio API error HTTP {resp.status_code}"
        err_code: Optional[int] = None
        try:
            err_json = resp.json()
            if isinstance(err_json, dict):
                if err_json.get("code") is not None:
                    try:
                        err_code = int(err_json["code"])
                    except (TypeError, ValueError):
                        err_code = None
                if err_json.get("message"):
                    err_detail = f"Twilio HTTP {resp.status_code}: {err_json['message']}"
        except Exception:
            pass
        if err_code in self.TRIAL_UNVERIFIED_ERROR_CODES:
            err_detail += (
                " [Twilio Trial: verify the recipient phone number in Twilio Console -> "
                "Verified Caller IDs]"
            )
        return err_detail[:500]

    async def _post_url(
        self, url: str, data: Dict[str, str], *, dispatch_mode: str = "REST"
    ) -> NotificationDispatchResult:
        cred_err = self._validate_credentials()
        if cred_err is not None:
            logger.warning("Twilio dispatch aborted: %s", cred_err)
            return NotificationDispatchResult(
                success=False,
                provider=self.provider_name,
                delivery_status=NotificationDeliveryStatus.FAILED,
                failure_reason=cred_err,
                is_simulated=False,
                trial_mode=self._trial_mode,
                dispatch_mode=dispatch_mode,
                attempts=1,
            )

        max_attempts = self._max_retries + 1
        last_failure = "Twilio dispatch failed"

        for attempt in range(1, max_attempts + 1):
            try:
                resp = await self._post_once(url, data)
            except httpx.TimeoutException:
                last_failure = f"Twilio API request timed out after {self._timeout_s}s"
                if attempt < max_attempts:
                    await asyncio.sleep(self._retry_delay(attempt))
                    continue
                return NotificationDispatchResult(
                    success=False,
                    provider=self.provider_name,
                    delivery_status=NotificationDeliveryStatus.FAILED,
                    failure_reason=last_failure,
                    is_simulated=False,
                    trial_mode=self._trial_mode,
                    dispatch_mode=dispatch_mode,
                    attempts=attempt,
                )
            except httpx.RequestError as exc:
                last_failure = f"Twilio network error: {type(exc).__name__}"
                if attempt < max_attempts:
                    await asyncio.sleep(self._retry_delay(attempt))
                    continue
                return NotificationDispatchResult(
                    success=False,
                    provider=self.provider_name,
                    delivery_status=NotificationDeliveryStatus.FAILED,
                    failure_reason=last_failure,
                    is_simulated=False,
                    trial_mode=self._trial_mode,
                    dispatch_mode=dispatch_mode,
                    attempts=attempt,
                )

            if resp.status_code in (401, 403):
                return NotificationDispatchResult(
                    success=False,
                    provider=self.provider_name,
                    delivery_status=NotificationDeliveryStatus.FAILED,
                    failure_reason=f"Twilio authentication failed (HTTP {resp.status_code})",
                    is_simulated=False,
                    trial_mode=self._trial_mode,
                    dispatch_mode=dispatch_mode,
                    attempts=attempt,
                )

            if resp.status_code in self.RETRYABLE_STATUS_CODES:
                last_failure = self._format_twilio_http_error(resp)
                if attempt < max_attempts:
                    delay = self._retry_delay(attempt, resp.headers.get("Retry-After"))
                    logger.warning(
                        "Twilio transient HTTP %s on attempt %d/%d; retrying in %.2fs",
                        resp.status_code,
                        attempt,
                        max_attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                return NotificationDispatchResult(
                    success=False,
                    provider=self.provider_name,
                    delivery_status=NotificationDeliveryStatus.FAILED,
                    failure_reason=last_failure,
                    is_simulated=False,
                    trial_mode=self._trial_mode,
                    dispatch_mode=dispatch_mode,
                    attempts=attempt,
                )

            if resp.status_code >= 400:
                return NotificationDispatchResult(
                    success=False,
                    provider=self.provider_name,
                    delivery_status=NotificationDeliveryStatus.FAILED,
                    failure_reason=self._format_twilio_http_error(resp),
                    is_simulated=False,
                    trial_mode=self._trial_mode,
                    dispatch_mode=dispatch_mode,
                    attempts=attempt,
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
                    is_simulated=False,
                    trial_mode=self._trial_mode,
                    dispatch_mode=dispatch_mode,
                    attempts=attempt,
                )
            except Exception:
                return NotificationDispatchResult(
                    success=False,
                    provider=self.provider_name,
                    delivery_status=NotificationDeliveryStatus.FAILED,
                    failure_reason="Invalid JSON response from Twilio API",
                    is_simulated=False,
                    trial_mode=self._trial_mode,
                    dispatch_mode=dispatch_mode,
                    attempts=attempt,
                )

        return NotificationDispatchResult(
            success=False,
            provider=self.provider_name,
            delivery_status=NotificationDeliveryStatus.FAILED,
            failure_reason=last_failure,
            is_simulated=False,
            trial_mode=self._trial_mode,
            dispatch_mode=dispatch_mode,
            attempts=max_attempts,
        )

    async def _post_form(
        self, endpoint: str, data: Dict[str, str]
    ) -> NotificationDispatchResult:
        url = f"{self.BASE_URL}/Accounts/{self._account_sid}/{endpoint}"
        return await self._post_url(url, data, dispatch_mode="REST")

    async def send_sms(
        self,
        to_number: str,
        body: str,
        status_callback_url: Optional[str] = None,
    ) -> NotificationDispatchResult:
        trial_err = self._check_trial_recipient(to_number, dispatch_mode="REST")
        if trial_err is not None:
            return trial_err
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
        trial_err = self._check_trial_recipient(to_number, dispatch_mode="REST")
        if trial_err is not None:
            return trial_err
        form: Dict[str, str] = {
            "To": to_number,
            "From": self._from_number,
            "Twiml": twiml,
        }
        if not self._trial_mode:
            form["MachineDetection"] = "Enable"
        if status_callback_url:
            form["StatusCallback"] = status_callback_url
            form["StatusCallbackEvent"] = "completed"
        result = await self._post_form("Calls.json", form)
        if (
            not result.success
            and "MachineDetection" in form
            and result.failure_reason
            and ("trial" in result.failure_reason.lower() or "disallowed parameters" in result.failure_reason.lower())
        ):
            logger.info("Twilio rejected MachineDetection on trial account; retrying voice call without MachineDetection.")
            form.pop("MachineDetection", None)
            result = await self._post_form("Calls.json", form)
        return result

    async def trigger_studio_workflow(
        self,
        to_number: str,
        parameters: Dict[str, Any],
        flow_sid: Optional[str] = None,
    ) -> NotificationDispatchResult:
        effective_flow_sid = (flow_sid or self._studio_flow_sid or "").strip()
        if not effective_flow_sid:
            return NotificationDispatchResult(
                success=False,
                provider=self.provider_name,
                delivery_status=NotificationDeliveryStatus.FAILED,
                failure_reason="Missing Twilio Studio Flow SID (NAVOS_TWILIO_STUDIO_FLOW_SID)",
                is_simulated=False,
                trial_mode=self._trial_mode,
                dispatch_mode="STUDIO",
                attempts=1,
            )
        trial_err = self._check_trial_recipient(to_number, dispatch_mode="STUDIO")
        if trial_err is not None:
            return trial_err
        url = f"{self.STUDIO_URL}/Flows/{effective_flow_sid}/Executions"
        form: Dict[str, str] = {
            "To": to_number,
            "From": self._from_number,
            "Parameters": json.dumps(parameters, ensure_ascii=False),
        }
        return await self._post_url(url, form, dispatch_mode="STUDIO")


def map_twilio_status(twilio_status: str) -> NotificationDeliveryStatus:
    """Map Twilio MessageStatus / CallStatus / Studio execution status strings."""
    normalized = (twilio_status or "").strip().lower()
    mapping = {
        "queued": NotificationDeliveryStatus.QUEUED,
        "accepted": NotificationDeliveryStatus.ACCEPTED,
        "sending": NotificationDeliveryStatus.REQUESTED,
        "sent": NotificationDeliveryStatus.SENT,
        "ringing": NotificationDeliveryStatus.RINGING,
        "in-progress": NotificationDeliveryStatus.IN_PROGRESS,
        "active": NotificationDeliveryStatus.IN_PROGRESS,
        "delivered": NotificationDeliveryStatus.DELIVERED,
        "completed": NotificationDeliveryStatus.COMPLETED,
        "ended": NotificationDeliveryStatus.COMPLETED,
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


def build_custom_test_voice_twiml(
    *,
    message: str,
    gather_action_url: Optional[str] = None,
) -> str:
    """
    Generate safely XML-escaped TwiML for custom/test automated voice verification.
    Includes `<Gather numDigits="1">` so keypad DTMF acknowledgement can be tested end-to-end.
    """
    safe_message = xml_escape((message or "").strip())
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
        f"{safe_message} "
        "Press 1 on your keypad to acknowledge this test alert, or press 2 to leave it unacknowledged."
        "</Say>"
        "</Gather>"
        "<Say voice=\"alice\">"
        "No keypad input was received. Goodbye."
        "</Say>"
        "</Response>"
    )

