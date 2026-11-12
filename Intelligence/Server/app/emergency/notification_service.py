"""
Phase 4: Emergency Notification Orchestration & Asynchronous Escalation Worker.

Coordinates resident and caregiver SMS/Voice notifications independently of
ESP32 actuator availability, persists delivery and human-acknowledgement states
separately in `EmergencyDatabase`, and escalates unacknowledged incidents across
priority-ordered caregivers.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from app.emergency.database import EmergencyDatabase, RecordNotFoundError
from app.emergency.decision_schemas import PolicyDecisionResult, ResponseCategory
from app.emergency.notification_provider import (
    NotificationDispatchResult,
    NotificationProvider,
    build_voice_twiml,
    create_ack_token,
    format_emergency_sms,
)
from app.emergency.response_policy import is_actuator_filtration_capable
from app.emergency.schemas import (
    ActuatorConnectionStatus,
    ActuatorState,
    ConsentStatus,
    EmergencyContactResponse,
    EmergencyEventResponse,
    EmergencyEventStatus,
    HumanAcknowledgementStatus,
    NotificationChannel,
    NotificationCreate,
    NotificationDeliveryStatus,
    NotificationResponse,
    ensure_utc,
    utc_now,
)

logger = logging.getLogger(__name__)


def _group_contacts_by_escalation_level(
    contacts: List[EmergencyContactResponse],
) -> Dict[int, List[EmergencyContactResponse]]:
    """
    Group active, consented contacts into:
      - Level 1: Primary caregiver (lowest priority number; ties broken by first)
      - Level 2: Secondary caregiver (next contact)
      - Level 3: Remaining registered caregiver contacts
    """
    eligible = [
        c
        for c in contacts
        if c.active_status and c.consent_status == ConsentStatus.GRANTED
    ]
    if not eligible:
        return {}

    groups: Dict[int, List[EmergencyContactResponse]] = {1: [eligible[0]]}
    if len(eligible) >= 2:
        groups[2] = [eligible[1]]
    if len(eligible) >= 3:
        groups[3] = eligible[2:]
    return groups


class EmergencyNotificationService:
    """
    Orchestrates emergency SMS/Voice notifications and caregiver escalation.
    """

    def __init__(
        self,
        *,
        emergency_db: EmergencyDatabase,
        provider: NotificationProvider,
        ack_signing_secret: str,
        public_webhook_base_url: Optional[str] = None,
        ack_timeout_s: float = 120.0,
        demo_ack_timeout_s: float = 30.0,
        demo_mode: bool = False,
    ) -> None:
        self.db = emergency_db
        self.provider = provider
        self.ack_signing_secret = ack_signing_secret
        self.public_webhook_base_url = (
            public_webhook_base_url.rstrip("/") if public_webhook_base_url else None
        )
        self.ack_timeout_s = ack_timeout_s
        self.demo_ack_timeout_s = demo_ack_timeout_s
        self.demo_mode = demo_mode
        self._background_tasks: Set[asyncio.Task[Any]] = set()

    @property
    def effective_ack_timeout_s(self) -> float:
        return self.demo_ack_timeout_s if self.demo_mode else self.ack_timeout_s

    def describe_actuator_status_for_node(self, node_id: str) -> str:
        """
        Return an honest, scientifically accurate summary of confirmed actuator
        status for caregiver alerts. Never claims an unfiltered fan purified air.
        """
        actuators = self.db.list_actuators_for_node(node_id)
        if not actuators:
            return "No wireless actuator registered; local UNO Q warning active."

        summaries: List[str] = []
        for act in actuators:
            if act.connection_status != ActuatorConnectionStatus.ONLINE:
                summaries.append(
                    f"{act.device_name} ({act.actuator_id}): OFFLINE/UNAVAILABLE"
                )
            elif not is_actuator_filtration_capable(act.actuator_type):
                summaries.append(
                    f"{act.device_name} ({act.actuator_id}): Unfiltered 5V fan "
                    f"(state={act.current_state.value}; NOT used for air purification)"
                )
            else:
                summaries.append(
                    f"{act.device_name} ({act.actuator_id}): Filtration unit "
                    f"({act.current_state.value})"
                )
        return "; ".join(summaries)

    def _build_callback_urls(
        self, notification_id: str, event_id: str
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        if not self.public_webhook_base_url:
            return None, None, None
        token = create_ack_token(
            secret=self.ack_signing_secret,
            event_id=event_id,
            notification_id=notification_id,
        )
        ack_url = f"{self.public_webhook_base_url}/api/v1/notifications/ack/{token}"
        status_url = f"{self.public_webhook_base_url}/api/v1/webhooks/twilio/status"
        gather_url = (
            f"{self.public_webhook_base_url}/api/v1/webhooks/twilio/voice/gather"
            f"?notification_id={notification_id}"
        )
        return ack_url, status_url, gather_url

    async def dispatch_for_event(
        self,
        event_id: str,
        *,
        escalation_level: Optional[int] = None,
    ) -> List[NotificationResponse]:
        """
        Dispatch SMS and/or Voice notifications for an emergency event at the
        specified escalation level (defaults to the event's current level).
        Prevents duplicate dispatches for the same `(event_id, contact_id, channel)`.
        """
        event = self.db.get_emergency_event(event_id)
        if event is None:
            raise RecordNotFoundError(f"EmergencyEvent '{event_id}' not found")

        if event.event_status in (
            EmergencyEventStatus.ACKNOWLEDGED,
            EmergencyEventStatus.RESOLVED,
            EmergencyEventStatus.CANCELLED,
        ):
            return []

        node = self.db.get_node(event.associated_node_id)
        resident_id = event.resident_id or (node.resident_id if node else None)
        if not resident_id:
            logger.warning(
                "Event '%s' (node '%s') has no associated resident; cannot notify contacts.",
                event_id,
                event.associated_node_id,
            )
            return []

        resident = self.db.get_resident(resident_id, include_safety_info=False)
        if resident is None or not resident.active_status:
            logger.warning("Resident '%s' not found or inactive for event '%s'", resident_id, event_id)
            return []
        if resident.consent_status != ConsentStatus.GRANTED:
            logger.warning(
                "Resident '%s' consent_status=%s; notifications suppressed.",
                resident_id,
                resident.consent_status.value,
            )
            return []

        contacts = self.db.list_contacts_for_resident(resident_id, active_only=True)
        grouped = _group_contacts_by_escalation_level(contacts)
        target_level = escalation_level if escalation_level is not None else max(1, event.escalation_level)
        target_contacts = grouped.get(target_level, [])
        if not target_contacts:
            return []

        existing_notifications = self.db.list_notifications_for_event(event_id)
        already_sent: Set[Tuple[str, NotificationChannel]] = {
            (n.contact_id, n.notification_channel) for n in existing_notifications
        }

        supp = event.supporting_measurements or {}
        pm25 = supp.get("pm2_5")
        pm10 = supp.get("pm10")
        gas_status = str(supp.get("gas_identity_candidate") or "UNESTABLISHED")
        system_response = self.describe_actuator_status_for_node(event.associated_node_id)
        location = resident.address_location or (node.location if node else None)
        detected_str = ensure_utc(event.detected_at).strftime("%Y-%m-%d %H:%M UTC")  # type: ignore[union-attr]

        dispatched: List[NotificationResponse] = []
        now = utc_now()

        for contact in target_contacts:
            for channel in contact.preferred_channels:
                if (contact.contact_id, channel) in already_sent:
                    continue

                ntf_id = f"ntf-{uuid.uuid4().hex[:12]}"
                ack_url, status_url, gather_url = self._build_callback_urls(
                    ntf_id, event_id
                )

                # Persist initial QUEUED record before external I/O
                self.db.create_notification(
                    NotificationCreate(
                        notification_id=ntf_id,
                        event_id=event_id,
                        contact_id=contact.contact_id,
                        notification_channel=channel,
                        provider=self.provider.provider_name,
                        delivery_status=NotificationDeliveryStatus.QUEUED,
                        acknowledgement_status=HumanAcknowledgementStatus.PENDING,
                    )
                )

                try:
                    if channel == NotificationChannel.SMS:
                        sms_body = format_emergency_sms(
                            hazard_classification=event.event_type,
                            severity=event.severity.value,
                            pm25=pm25,
                            pm10=pm10,
                            gas_status=gas_status,
                            system_response=system_response,
                            event_id=event_id,
                            location=location,
                            detected_at_str=detected_str,
                            ack_url=ack_url,
                        )
                        result = await self.provider.send_sms(
                            to_number=contact.phone_number,
                            body=sms_body,
                            status_callback_url=status_url,
                        )
                    else:  # VOICE_CALL
                        twiml = build_voice_twiml(
                            hazard_classification=event.event_type,
                            severity=event.severity.value,
                            system_response=system_response,
                            gather_action_url=gather_url,
                            location=location,
                        )
                        result = await self.provider.make_voice_call(
                            to_number=contact.phone_number,
                            twiml=twiml,
                            status_callback_url=status_url,
                        )
                except Exception as exc:
                    result = NotificationDispatchResult(
                        success=False,
                        provider=self.provider.provider_name,
                        delivery_status=NotificationDeliveryStatus.FAILED,
                        failure_reason=f"Unexpected dispatch error: {type(exc).__name__}",
                    )

                updated = self.db.update_notification_delivery(
                    notification_id=ntf_id,
                    delivery_status=result.delivery_status,
                    provider_reference_id=result.provider_reference_id,
                    sent_at=now if result.success else None,
                    failure_reason=result.failure_reason,
                )
                dispatched.append(updated)
                already_sent.add((contact.contact_id, channel))

        # Update event status & escalation metadata
        meta = dict(event.event_metadata or {})
        meta[f"level_{target_level}_dispatched_at"] = now.isoformat()
        meta["last_notification_dispatch_at"] = now.isoformat()
        new_status = (
            EmergencyEventStatus.ESCALATING
            if target_level > 1
            else EmergencyEventStatus.ACTIVE_UNACKNOWLEDGED
        )
        self.db.update_emergency_event_lifecycle(
            event_id,
            event_status=new_status,
            escalation_level=target_level,
            event_metadata=meta,
        )
        return dispatched

    def enqueue_policy_notification(
        self, decision: PolicyDecisionResult
    ) -> Optional[asyncio.Task[Any]]:
        """
        Non-blocking fire-and-forget enqueue for `ProcessingService`.
        Never blocks sensor ingestion while waiting on Twilio.
        """
        if not decision.active_event_id:
            return None
        if ResponseCategory.EMERGENCY_NOTIFICATION not in decision.recommended_responses:
            return None

        event = self.db.get_emergency_event(decision.active_event_id)
        if event is None:
            return None

        # Only trigger initial dispatch if no notifications exist yet for this event
        if self.db.list_notifications_for_event(event.event_id):
            return None

        async def _runner() -> None:
            try:
                await self.dispatch_for_event(event.event_id, escalation_level=1)
            except Exception as exc:
                logger.error(
                    "Background notification dispatch failed for event %s: %s",
                    event.event_id,
                    exc,
                )

        task = asyncio.create_task(_runner())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def drain_background_tasks(self, timeout_s: float = 5.0) -> None:
        """Await pending background notification tasks during graceful shutdown."""
        pending = [t for t in self._background_tasks if not t.done()]
        if not pending:
            return
        done, still_pending = await asyncio.wait(pending, timeout=timeout_s)
        for task in still_pending:
            task.cancel()
        if still_pending:
            logger.warning(
                "Cancelled %d background notification task(s) after %.1fs shutdown timeout",
                len(still_pending),
                timeout_s,
            )

    def record_human_acknowledgement(
        self,
        *,
        notification_id: str,
        acknowledgement_status: HumanAcknowledgementStatus = HumanAcknowledgementStatus.ACKNOWLEDGED,
        acknowledged_at: Optional[datetime] = None,
        source: str = "API",
    ) -> NotificationResponse:
        """
        Record explicit human acknowledgement on both the notification record
        and its parent emergency event, halting further escalation.
        """
        ack_dt = ensure_utc(acknowledged_at) or utc_now()
        updated_ntf = self.db.acknowledge_notification_by_human(
            notification_id=notification_id,
            acknowledgement_status=acknowledgement_status,
            acknowledged_at=ack_dt,
        )
        event = self.db.get_emergency_event(updated_ntf.event_id)
        if event is not None and event.event_status not in (
            EmergencyEventStatus.RESOLVED,
            EmergencyEventStatus.CANCELLED,
        ):
            meta = dict(event.event_metadata or {})
            meta["acknowledged_via"] = source
            meta["acknowledged_notification_id"] = notification_id
            self.db.update_emergency_event_lifecycle(
                event.event_id,
                event_status=EmergencyEventStatus.ACKNOWLEDGED,
                acknowledged_at=ack_dt,
                event_metadata=meta,
            )
        return updated_ntf

    def resolve_event_manually(
        self, event_id: str, *, resolved_by: str = "operator", notes: Optional[str] = None
    ) -> EmergencyEventResponse:
        """
        Explicitly mark an emergency event RESOLVED.
        Never automatically resolves an unacknowledged incident merely because
        air quality improved.
        """
        event = self.db.get_emergency_event(event_id)
        if event is None:
            raise RecordNotFoundError(f"EmergencyEvent '{event_id}' not found")
        now = utc_now()
        meta = dict(event.event_metadata or {})
        meta["resolved_by"] = resolved_by
        if notes:
            meta["resolution_notes"] = notes
        return self.db.update_emergency_event_lifecycle(
            event_id,
            event_status=EmergencyEventStatus.RESOLVED,
            resolved_at=now,
            event_metadata=meta,
        )

    async def check_and_escalate_once(
        self, *, now: Optional[datetime] = None
    ) -> List[NotificationResponse]:
        """
        Evaluate all unresolved, unacknowledged events and escalate to the next
        caregiver priority tier if `effective_ack_timeout_s` has elapsed.
        """
        ref_now = ensure_utc(now) or utc_now()
        timeout_delta = timedelta(seconds=self.effective_ack_timeout_s)
        escalated_notifications: List[NotificationResponse] = []

        for event in self.db.list_unresolved_emergency_events():
            if event.event_status == EmergencyEventStatus.ACKNOWLEDGED:
                continue

            existing = self.db.list_notifications_for_event(event.event_id)
            if not existing:
                # Durable restart recovery: if process crashed after event creation
                # but before Level 1 dispatch completed, recover and dispatch Level 1.
                if (
                    event.event_status
                    in (
                        EmergencyEventStatus.DETECTED,
                        EmergencyEventStatus.ACTIVE_UNACKNOWLEDGED,
                        EmergencyEventStatus.ESCALATING,
                    )
                    and event.escalation_level >= 1
                ):
                    recovered = await self.dispatch_for_event(
                        event.event_id, escalation_level=1
                    )
                    escalated_notifications.extend(recovered)
                continue
            if any(
                n.acknowledgement_status
                in (
                    HumanAcknowledgementStatus.ACKNOWLEDGED,
                    HumanAcknowledgementStatus.CHECKED_ON,
                )
                for n in existing
            ):
                continue

            meta = dict(event.event_metadata or {})
            if meta.get("all_contacts_exhausted"):
                continue

            last_dispatch_iso = meta.get("last_notification_dispatch_at")
            if last_dispatch_iso:
                last_dispatch = ensure_utc(datetime.fromisoformat(last_dispatch_iso))
            else:
                last_dispatch = ensure_utc(existing[-1].created_at)

            if last_dispatch is None or (ref_now - last_dispatch) < timeout_delta:
                continue

            node = self.db.get_node(event.associated_node_id)
            resident_id = event.resident_id or (node.resident_id if node else None)
            if not resident_id:
                continue

            contacts = self.db.list_contacts_for_resident(resident_id, active_only=True)
            grouped = _group_contacts_by_escalation_level(contacts)
            next_level = event.escalation_level + 1

            if next_level not in grouped:
                meta["all_contacts_exhausted"] = True
                meta["exhausted_at"] = ref_now.isoformat()
                self.db.update_emergency_event_lifecycle(
                    event.event_id,
                    event_metadata=meta,
                )
                logger.warning(
                    "All caregiver contacts exhausted without acknowledgement for event '%s'",
                    event.event_id,
                )
                continue

            new_ntfs = await self.dispatch_for_event(
                event.event_id, escalation_level=next_level
            )
            escalated_notifications.extend(new_ntfs)

        return escalated_notifications


class EscalationWorker:
    """Background asyncio worker polling `check_and_escalate_once()`."""

    def __init__(
        self,
        notification_service: EmergencyNotificationService,
        poll_interval_s: float = 5.0,
    ) -> None:
        self.notification_service = notification_service
        self.poll_interval_s = poll_interval_s
        self._task: Optional[asyncio.Task[None]] = None
        self._stop_event = asyncio.Event()

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.notification_service.check_and_escalate_once()
            except Exception as exc:
                logger.error("EscalationWorker iteration error: %s", exc)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.poll_interval_s
                )
            except asyncio.TimeoutError:
                continue

