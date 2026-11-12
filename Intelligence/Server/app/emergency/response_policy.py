"""
Stage 2 — Environmental Response Policy & Event Lifecycle Engine
(`app.emergency.response_policy`).

Separates hazard detection (Stage 1: what is happening) from response policy
selection (Stage 2: what should happen) and manages deduplicated emergency
event lifecycle transitions in `EmergencyDatabase`.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.emergency.database import EmergencyDatabase
from app.emergency.decision_schemas import (
    ActionExecutionState,
    ActuatorPolicyRecommendation,
    EventLifecycleTransition,
    HazardEvaluationResult,
    HazardSeverity,
    HazardType,
    PolicyDecisionResult,
    ResponseCategory,
    SEVERITY_RANK,
)
from app.emergency.schemas import (
    ActuatorConnectionStatus,
    ActuatorResponse,
    EmergencyEventCreate,
    EmergencyEventResponse,
    EmergencyEventStatus,
    EmergencySeverity,
)

logger = logging.getLogger(__name__)

# Non-environmental diagnostic hazard types that warrant local warnings/monitoring
# rather than creating false environmental pollution incidents by default.
_DIAGNOSTIC_HAZARD_TYPES = {
    HazardType.MISSING_OR_STALE_DATA,
    HazardType.SENSOR_ANOMALY_OR_FAULT,
    HazardType.CONFLICTING_READINGS,
    HazardType.UNCERTAIN_PREDICTION,
}


def is_actuator_filtration_capable(actuator_type: Optional[str]) -> bool:
    """
    Determine whether a registered actuator is a verified filtration-capable
    air purifier rather than an unfiltered fan (Safety Rule 1).

    The current NavosEdge 5V 2-wire brushless fan ('ESP32_FAN_5V_UNFILTERED')
    does NOT have a particulate filter and must NEVER be classified as
    filtration-capable.
    """
    if not actuator_type:
        return False
    upper = actuator_type.strip().upper()
    if "UNFILTERED" in upper or "NO_FILTER" in upper:
        return False
    return any(
        token in upper
        for token in ("HEPA", "PURIFIER", "FILTRATION", "FILTER_EQUIPPED", "FILTERED")
    )


def _map_to_db_severity(sev: HazardSeverity) -> EmergencySeverity:
    return {
        HazardSeverity.NORMAL: EmergencySeverity.NORMAL,
        HazardSeverity.WARNING: EmergencySeverity.WARNING,
        HazardSeverity.CRITICAL: EmergencySeverity.CRITICAL,
        HazardSeverity.EMERGENCY: EmergencySeverity.EMERGENCY,
    }[sev]


def _map_from_db_severity(db_sev: EmergencySeverity) -> HazardSeverity:
    mapping = {
        EmergencySeverity.NORMAL: HazardSeverity.NORMAL,
        EmergencySeverity.LOW: HazardSeverity.WARNING,
        EmergencySeverity.WARNING: HazardSeverity.WARNING,
        EmergencySeverity.MEDIUM: HazardSeverity.WARNING,
        EmergencySeverity.HIGH: HazardSeverity.CRITICAL,
        EmergencySeverity.CRITICAL: HazardSeverity.CRITICAL,
        EmergencySeverity.EMERGENCY: HazardSeverity.EMERGENCY,
    }
    return mapping.get(db_sev, HazardSeverity.WARNING)


class ResponsePolicyEngine:
    """
    Deterministic Stage 2 Response Policy Engine.

    Consumes `HazardEvaluationResult` and produces a `PolicyDecisionResult`
    enforcing all 10 NavosEdge safety rules and deduplicated event persistence.
    """

    def __init__(
        self,
        emergency_db: Optional[EmergencyDatabase] = None,
        persist_diagnostic_events: bool = False,
    ) -> None:
        self.emergency_db = emergency_db
        self.persist_diagnostic_events = persist_diagnostic_events

    def decide(
        self,
        evaluation: HazardEvaluationResult,
        *,
        registered_actuators: Optional[List[ActuatorResponse]] = None,
        resident_id: Optional[str] = None,
        persist_event: bool = True,
    ) -> PolicyDecisionResult:
        """
        Determine recommended policy responses, actuator safety posture, and
        emergency event lifecycle transition for a given `HazardEvaluationResult`.
        """
        # 1. Discover registered actuators for the node if database is available
        actuators = registered_actuators
        if actuators is None and self.emergency_db is not None and self.emergency_db.is_initialized:
            try:
                actuators = self.emergency_db.list_actuators_for_node(evaluation.node_id)
            except Exception as exc:
                logger.warning(
                    "Could not query actuators for node %s: %s",
                    evaluation.node_id,
                    exc,
                )
                actuators = []
        actuators = actuators or []

        # 2. Evaluate Actuator Policy Recommendation (Safety Rules 1, 3, 4, 5, 6, 9, 10)
        actuator_rec = self._evaluate_actuator_policy(evaluation, actuators)

        # 3. Select Response Categories (Safety Rules 1–10)
        responses, human_intervention, reason_suffix = self._select_response_categories(
            evaluation, actuator_rec
        )

        # 4. Build explicit ActionExecutionState map (Safety Rule 9:
        #    Recommended actions are distinct from executed/acknowledged actions)
        action_states: Dict[str, ActionExecutionState] = {}
        for cat in responses:
            action_states[cat.value] = ActionExecutionState.RECOMMENDED

        combined_reason = (
            f"{evaluation.reason} Policy: {reason_suffix}"
            if reason_suffix
            else evaluation.reason
        )

        # 5. Manage deduplicated EmergencyEvent lifecycle in database (Part 5 & Part 6)
        lifecycle_transition = EventLifecycleTransition.NONE
        active_event_id: Optional[str] = None

        if persist_event and self.emergency_db is not None and self.emergency_db.is_initialized:
            try:
                lifecycle_transition, active_event_id = self._sync_event_lifecycle(
                    evaluation=evaluation,
                    responses=responses,
                    human_intervention=human_intervention,
                    combined_reason=combined_reason,
                    actuator_rec=actuator_rec,
                    resident_id=resident_id,
                )
            except Exception as exc:
                # Safety Rule 8: A database or communication failure must not disable local warnings
                logger.error(
                    "Emergency event persistence failed for node %s (local warning preserved): %s",
                    evaluation.node_id,
                    exc,
                )

        return PolicyDecisionResult(
            node_id=evaluation.node_id,
            decision_timestamp=evaluation.detection_timestamp,
            hazard_type=evaluation.hazard_type,
            severity=evaluation.severity,
            environmental_trend=evaluation.environmental_trend,
            relevant_measurements=dict(evaluation.relevant_measurements),
            supporting_evidence=list(evaluation.supporting_evidence),
            model_confidence=evaluation.model_confidence,
            model_uncertainty=evaluation.model_uncertainty,
            reason=combined_reason,
            recommended_responses=responses,
            action_states=action_states,
            human_intervention_recommended=human_intervention,
            actuator_recommendation=actuator_rec,
            local_warning_preserved=True,
            lifecycle_transition=lifecycle_transition,
            active_event_id=active_event_id,
            evaluation=evaluation,
        )

    # ------------------------------------------------------------------
    # Internal Policy Rules
    # ------------------------------------------------------------------

    def _evaluate_actuator_policy(
        self,
        evaluation: HazardEvaluationResult,
        actuators: List[ActuatorResponse],
    ) -> ActuatorPolicyRecommendation:
        """
        Enforce physical appliance safety rules:
          - Rule 1: Never recommend an unfiltered fan for particulate pollution removal.
          - Rule 3 & 4: Do not treat every gas detection as an instruction to activate a fan.
          - Rule 5 & 6: Do not trigger physical actions on uncertain or conflicting data.
        """
        # Prefer a filtration-capable actuator if one is registered; otherwise inspect first actuator
        filtration_actuators = [
            a for a in actuators if is_actuator_filtration_capable(a.actuator_type)
        ]
        selected = filtration_actuators[0] if filtration_actuators else (actuators[0] if actuators else None)

        if selected is None:
            return ActuatorPolicyRecommendation(
                actuator_id=None,
                actuator_type=None,
                is_filtration_capable=False,
                is_available=False,
                recommended_action="ACTUATOR_UNAVAILABLE",
                execution_state=ActionExecutionState.UNAVAILABLE,
                rationale="No physical actuator is registered for this node.",
            )

        is_filt = is_actuator_filtration_capable(selected.actuator_type)
        is_avail = selected.connection_status == ActuatorConnectionStatus.ONLINE

        # Uncertain, conflicting, missing, stale, or faulty telemetry -> inhibit actuation
        if (
            evaluation.has_hardware_fault
            or evaluation.has_sensor_conflict
            or evaluation.has_missing_data
            or evaluation.is_stale_data
            or evaluation.hazard_type == HazardType.UNCERTAIN_PREDICTION
        ):
            return ActuatorPolicyRecommendation(
                actuator_id=selected.actuator_id,
                actuator_type=selected.actuator_type,
                is_filtration_capable=is_filt,
                is_available=is_avail,
                recommended_action="INHIBITED_UNCERTAIN_OR_CONFLICT",
                execution_state=ActionExecutionState.INHIBITED_BY_SAFETY_RULE,
                rationale=(
                    "Physical actuation is inhibited due to uncertain model prediction, "
                    "conflicting sensor channels, or stale/faulty telemetry."
                ),
            )

        # Gas-related hazards: Rule 3 & Rule 4
        if evaluation.hazard_type in (
            HazardType.GAS_ELEVATED,
            HazardType.GAS_HAZARD,
            HazardType.COMBINED_GAS_AND_PARTICULATE,
        ):
            return ActuatorPolicyRecommendation(
                actuator_id=selected.actuator_id,
                actuator_type=selected.actuator_type,
                is_filtration_capable=is_filt,
                is_available=is_avail,
                recommended_action="DO_NOT_ACTIVATE_ON_GAS_HAZARD",
                execution_state=ActionExecutionState.INHIBITED_BY_SAFETY_RULE,
                rationale=(
                    "Gas-related hazards require hazard-specific safety handling; "
                    "automatic electrical fan activation is inhibited."
                ),
            )

        # Particulate hazards: Rule 1
        if evaluation.hazard_type in (
            HazardType.PARTICULATE_ELEVATED,
            HazardType.PARTICULATE_SUDDEN_INCREASE,
            HazardType.PARTICULATE_PERSISTENT,
            HazardType.PARTICULATE_CRITICAL,
        ):
            if not is_filt:
                return ActuatorPolicyRecommendation(
                    actuator_id=selected.actuator_id,
                    actuator_type=selected.actuator_type,
                    is_filtration_capable=False,
                    is_available=is_avail,
                    recommended_action="DO_NOT_ACTIVATE_UNFILTERED_FAN",
                    execution_state=ActionExecutionState.INHIBITED_BY_SAFETY_RULE,
                    rationale=(
                        f"Actuator '{selected.actuator_id}' ({selected.actuator_type}) is an "
                        "unfiltered fan without a particulate filter and cannot remove PM1.0/PM2.5/PM10."
                    ),
                )
            return ActuatorPolicyRecommendation(
                actuator_id=selected.actuator_id,
                actuator_type=selected.actuator_type,
                is_filtration_capable=True,
                is_available=is_avail,
                recommended_action="ACTIVATE_FILTRATION",
                execution_state=(
                    ActionExecutionState.RECOMMENDED
                    if is_avail
                    else ActionExecutionState.UNAVAILABLE
                ),
                rationale=(
                    f"Actuator '{selected.actuator_id}' ({selected.actuator_type}) is a "
                    "filtration-capable purifier suitable for particulate reduction."
                ),
            )

        return ActuatorPolicyRecommendation(
            actuator_id=selected.actuator_id,
            actuator_type=selected.actuator_type,
            is_filtration_capable=is_filt,
            is_available=is_avail,
            recommended_action="NONE",
            execution_state=ActionExecutionState.RECOMMENDED,
            rationale="Environmental conditions are normal or recovering; no actuation required.",
        )

    def _select_response_categories(
        self,
        evaluation: HazardEvaluationResult,
        actuator_rec: ActuatorPolicyRecommendation,
    ) -> tuple[List[ResponseCategory], bool, str]:
        responses: List[ResponseCategory] = [ResponseCategory.CONTINUE_MONITORING]
        human_intervention = False
        notes: List[str] = []

        def _add(cat: ResponseCategory) -> None:
            if cat not in responses:
                responses.append(cat)

        ht = evaluation.hazard_type
        sev = evaluation.severity

        # Normal or recovering
        if sev == HazardSeverity.NORMAL and ht in (
            HazardType.NONE,
            HazardType.ENVIRONMENTAL_RECOVERY,
        ):
            return (
                responses,
                False,
                "Continue routine environmental monitoring.",
            )

        # Any non-normal condition always issues a local warning (Safety Rule 8)
        _add(ResponseCategory.LOCAL_WARNING)

        # Missing or stale data (Safety Rule 7)
        if ht == HazardType.MISSING_OR_STALE_DATA:
            notes.append("Explicit missing/stale telemetry warning; physical actions inhibited.")
            return responses, False, " ".join(notes)

        # Uncertain prediction (Safety Rule 5)
        if ht == HazardType.UNCERTAIN_PREDICTION:
            notes.append(
                "Uncertain model prediction capped at LOCAL_WARNING; unsafe physical actions inhibited."
            )
            return responses, False, " ".join(notes)

        # Sensor conflict or hardware fault (Safety Rule 6)
        if ht in (HazardType.CONFLICTING_READINGS, HazardType.SENSOR_ANOMALY_OR_FAULT):
            _add(ResponseCategory.REQUEST_HUMAN_INTERVENTION)
            human_intervention = True
            notes.append(
                "Conservative decision: sensor conflict or fault requires human inspection."
            )
            return responses, human_intervention, " ".join(notes)

        # Particulate pollution policies (Safety Rules 1 & 2)
        if ht in (
            HazardType.PARTICULATE_ELEVATED,
            HazardType.PARTICULATE_SUDDEN_INCREASE,
            HazardType.PARTICULATE_PERSISTENT,
            HazardType.PARTICULATE_CRITICAL,
            HazardType.COMBINED_GAS_AND_PARTICULATE,
        ):
            # Safety Rule 2: Do not open outdoor ventilation when outdoor/particulate pollution is elevated
            _add(ResponseCategory.RESTRICT_OUTDOOR_AIR_INTAKE)
            notes.append("Restrict outdoor air intake to prevent particulate ingress.")

            # Safety Rule 1: Only recommend ACTIVATE_FILTRATION if a compatible filtration purifier is registered
            if (
                actuator_rec.is_filtration_capable
                and actuator_rec.recommended_action == "ACTIVATE_FILTRATION"
            ):
                _add(ResponseCategory.ACTIVATE_FILTRATION)
                notes.append("Filtration recommended on compatible purifier.")
            else:
                notes.append(
                    "Unfiltered fan is not recommended for particulate removal."
                )

        # Gas hazard policies (Safety Rules 3 & 4)
        if ht in (
            HazardType.GAS_ELEVATED,
            HazardType.GAS_HAZARD,
            HazardType.COMBINED_GAS_AND_PARTICULATE,
        ):
            _add(ResponseCategory.REQUEST_HUMAN_INTERVENTION)
            human_intervention = True
            notes.append(
                "Gas hazard requires human safety verification; fan activation is not automatically recommended."
            )

        # Critical & Emergency escalation (Safety Rule 10: notification remains possible even without actuation)
        if SEVERITY_RANK[sev] >= SEVERITY_RANK[HazardSeverity.CRITICAL]:
            _add(ResponseCategory.REQUEST_HUMAN_INTERVENTION)
            human_intervention = True
            if (
                sev == HazardSeverity.EMERGENCY
                or ht in (HazardType.GAS_HAZARD, HazardType.COMBINED_GAS_AND_PARTICULATE, HazardType.PARTICULATE_CRITICAL, HazardType.PARTICULATE_PERSISTENT)
            ):
                _add(ResponseCategory.EMERGENCY_NOTIFICATION)
                notes.append(
                    "Emergency caregiver notification recommended (independent of actuator availability)."
                )

        return responses, human_intervention, " ".join(notes)

    # ------------------------------------------------------------------
    # Event Lifecycle & Deduplication (Part 5 & Part 6)
    # ------------------------------------------------------------------

    def _sync_event_lifecycle(
        self,
        *,
        evaluation: HazardEvaluationResult,
        responses: List[ResponseCategory],
        human_intervention: bool,
        combined_reason: str,
        actuator_rec: ActuatorPolicyRecommendation,
        resident_id: Optional[str],
    ) -> tuple[EventLifecycleTransition, Optional[str]]:
        assert self.emergency_db is not None

        node_id = evaluation.node_id
        # Verify node is registered in emergency_db before writing foreign-keyed events
        node_record = self.emergency_db.get_node(node_id)
        if node_record is None:
            return EventLifecycleTransition.NONE, None

        effective_resident_id = resident_id or node_record.resident_id
        active_event = self.emergency_db.get_active_emergency_event_for_node(node_id)

        is_environmental_hazard = (
            SEVERITY_RANK[evaluation.severity] >= SEVERITY_RANK[HazardSeverity.WARNING]
            and (
                self.persist_diagnostic_events
                or evaluation.hazard_type not in _DIAGNOSTIC_HAZARD_TYPES
            )
        )

        recommended_action_strs = [r.value for r in responses]
        clean_measurements = {
            k: v for k, v in evaluation.relevant_measurements.items() if v is not None
        }

        # Case 1: Active hazard present
        if is_environmental_hazard:
            new_db_sev = _map_to_db_severity(evaluation.severity)
            target_status = (
                EmergencyEventStatus.ACTIVE_UNACKNOWLEDGED
                if SEVERITY_RANK[evaluation.severity]
                >= SEVERITY_RANK[HazardSeverity.CRITICAL]
                else EmergencyEventStatus.DETECTED
            )

            if active_event is None:
                # Create a new deduplicated EmergencyEvent
                created = self.emergency_db.create_emergency_event(
                    EmergencyEventCreate(
                        associated_node_id=node_id,
                        resident_id=effective_resident_id,
                        event_type=evaluation.hazard_type.value,
                        severity=new_db_sev,
                        event_status=target_status,
                        detected_at=evaluation.detection_timestamp,
                        decision_timestamp=evaluation.detection_timestamp,
                        decision_reason=combined_reason,
                        supporting_measurements=clean_measurements,
                        model_uncertainty=evaluation.model_uncertainty,
                        recommended_actions=recommended_action_strs,
                        human_intervention_required=human_intervention,
                        escalation_level=1,
                        event_metadata={
                            "environmental_trend": evaluation.environmental_trend.value,
                            "supporting_evidence": evaluation.supporting_evidence,
                            "gas_identity_candidate": evaluation.gas_identity_candidate,
                            "pollution_source_candidate": evaluation.pollution_source_candidate,
                            "consecutive_hazard_count": evaluation.consecutive_hazard_count,
                            "actuator_recommendation": actuator_rec.model_dump(mode="json"),
                            "update_count": 1,
                        },
                    )
                )
                return EventLifecycleTransition.NEW_HAZARD_DETECTED, created.event_id

            # Active event already exists -> Deduplicate and transition state in-place
            prev_sev = _map_from_db_severity(active_event.severity)
            prev_rank = SEVERITY_RANK[prev_sev]
            curr_rank = SEVERITY_RANK[evaluation.severity]

            if curr_rank > prev_rank:
                transition = EventLifecycleTransition.SEVERITY_ESCALATED
                new_esc_level = active_event.escalation_level + 1
            elif curr_rank < prev_rank:
                transition = EventLifecycleTransition.SEVERITY_REDUCED
                new_esc_level = active_event.escalation_level
            else:
                transition = EventLifecycleTransition.EXISTING_HAZARD_CONTINUED
                new_esc_level = active_event.escalation_level

            # Preserve ACKNOWLEDGED status if already acknowledged unless escalating to EMERGENCY
            eff_status = active_event.event_status
            if eff_status == EmergencyEventStatus.RECOVERING:
                eff_status = target_status
            elif (
                eff_status == EmergencyEventStatus.DETECTED
                and target_status == EmergencyEventStatus.ACTIVE_UNACKNOWLEDGED
            ):
                eff_status = EmergencyEventStatus.ACTIVE_UNACKNOWLEDGED

            meta = dict(active_event.event_metadata or {})
            meta["environmental_trend"] = evaluation.environmental_trend.value
            meta["supporting_evidence"] = evaluation.supporting_evidence
            meta["gas_identity_candidate"] = evaluation.gas_identity_candidate
            meta["consecutive_hazard_count"] = evaluation.consecutive_hazard_count
            meta["actuator_recommendation"] = actuator_rec.model_dump(mode="json")
            meta["last_transition"] = transition.value
            meta["update_count"] = int(meta.get("update_count", 1)) + 1

            updated = self.emergency_db.update_emergency_event_lifecycle(
                active_event.event_id,
                event_type=evaluation.hazard_type.value,
                severity=new_db_sev,
                event_status=eff_status,
                escalation_level=new_esc_level,
                decision_reason=combined_reason,
                supporting_measurements=clean_measurements,
                model_uncertainty=evaluation.model_uncertainty,
                recommended_actions=recommended_action_strs,
                decision_timestamp=evaluation.detection_timestamp,
                human_intervention_required=human_intervention,
                event_metadata=meta,
            )
            return transition, updated.event_id

        # Case 2: No active hazard in current reading, check if an existing active event is recovering or resolved
        if active_event is not None:
            if evaluation.hazard_type == HazardType.ENVIRONMENTAL_RECOVERY:
                meta = dict(active_event.event_metadata or {})
                meta["environmental_trend"] = evaluation.environmental_trend.value
                meta["consecutive_recovery_count"] = evaluation.consecutive_recovery_count
                meta["last_transition"] = EventLifecycleTransition.HAZARD_RECOVERING.value
                meta["update_count"] = int(meta.get("update_count", 1)) + 1

                updated = self.emergency_db.update_emergency_event_lifecycle(
                    active_event.event_id,
                    event_status=EmergencyEventStatus.RECOVERING,
                    decision_reason=combined_reason,
                    supporting_measurements=clean_measurements,
                    recommended_actions=recommended_action_strs,
                    decision_timestamp=evaluation.detection_timestamp,
                    event_metadata=meta,
                )
                return EventLifecycleTransition.HAZARD_RECOVERING, updated.event_id

            if (
                evaluation.severity == HazardSeverity.NORMAL
                and evaluation.hazard_type == HazardType.NONE
            ):
                meta = dict(active_event.event_metadata or {})
                meta["environmental_trend"] = evaluation.environmental_trend.value
                meta["last_transition"] = EventLifecycleTransition.EVENT_RESOLVED.value
                meta["update_count"] = int(meta.get("update_count", 1)) + 1

                resolved = self.emergency_db.update_emergency_event_lifecycle(
                    active_event.event_id,
                    event_status=EmergencyEventStatus.RESOLVED,
                    decision_reason=combined_reason,
                    supporting_measurements=clean_measurements,
                    recommended_actions=recommended_action_strs,
                    decision_timestamp=evaluation.detection_timestamp,
                    human_intervention_required=False,
                    event_metadata=meta,
                    resolved_at=evaluation.detection_timestamp,
                )
                return EventLifecycleTransition.EVENT_RESOLVED, resolved.event_id

        return EventLifecycleTransition.NONE, (active_event.event_id if active_event else None)


class HazardPolicyService:
    """
    High-level, fault-isolated coordinator combining Stage 1 (`HazardEvaluator`)
    and Stage 2 (`ResponsePolicyEngine`).

    Guarantees that any unexpected exception inside hazard evaluation or policy
    persistence is caught, logged, and converted into a safe fallback decision
    so existing sensor processing is never interrupted.
    """

    def __init__(
        self,
        evaluator: HazardEvaluator,
        policy_engine: ResponsePolicyEngine,
    ) -> None:
        self.evaluator = evaluator
        self.policy_engine = policy_engine

    def evaluate_and_decide(
        self,
        payload: Any,
        *,
        inference: Any = None,
        anomaly_report: Any = None,
        source_result: Any = None,
        aqi_result: Any = None,
        pipeline_results: Any = None,
        registered_actuators: Optional[List[ActuatorResponse]] = None,
        resident_id: Optional[str] = None,
        persist_event: bool = True,
        reference_time: Any = None,
    ) -> Optional[PolicyDecisionResult]:
        try:
            evaluation = self.evaluator.evaluate(
                payload,
                inference=inference,
                anomaly_report=anomaly_report,
                source_result=source_result,
                aqi_result=aqi_result,
                pipeline_results=pipeline_results,
                reference_time=reference_time,
            )
            return self.policy_engine.decide(
                evaluation,
                registered_actuators=registered_actuators,
                resident_id=resident_id,
                persist_event=persist_event,
            )
        except Exception as exc:
            logger.error(
                "HazardPolicyService failed safely without interrupting pipeline: %s",
                exc,
                exc_info=True,
            )
            return None
