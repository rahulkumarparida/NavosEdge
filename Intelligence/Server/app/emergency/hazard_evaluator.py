"""
Stage 1 — Environmental Hazard Evaluator (`app.emergency.hazard_evaluator`).

Consumes telemetry and existing NavosEdge intelligence outputs (SensorSafetyGate,
TinyGasNet MC-Dropout inference, AnomalyEngine EMA/OLS/MAD reports,
SourceClassifier, and AQIService) to determine WHAT is happening in the
environment without coupling to physical appliance execution.
"""

from __future__ import annotations

import logging
import math
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional, Tuple, Union

from app.advisory.rules import AdvisoryConfig
from app.aqi.schemas import AQICalculationResult
from app.core.config import Settings, get_settings
from app.emergency.decision_schemas import (
    EnvironmentalTrend,
    HazardEvaluationResult,
    HazardSeverity,
    HazardType,
    SEVERITY_RANK,
)
from app.emergency.schemas import ensure_utc, utc_now
from app.schemas.anomaly import AnomalyReport
from app.schemas.inference import InferenceResult, InferenceStatus
from app.schemas.pipeline import PipelineResults
from app.schemas.sensor import SensorPayload
from app.services.safety_gate import SensorSafetyGate

logger = logging.getLogger(__name__)


@dataclass
class _ObservationSnapshot:
    timestamp: datetime
    pm1_0: Optional[float]
    pm2_5: Optional[float]
    pm10: Optional[float]
    mq2_v: Optional[float]
    mq9_v: Optional[float]
    mq135_v: Optional[float]
    temperature_c: Optional[float]
    humidity_pct: Optional[float]
    severity: HazardSeverity
    hazard_type: HazardType


@dataclass
class _NodeEvaluationHistory:
    snapshots: Deque[_ObservationSnapshot] = field(
        default_factory=lambda: deque(maxlen=25)
    )
    consecutive_hazard_count: int = 0
    consecutive_critical_count: int = 0
    consecutive_recovery_count: int = 0
    had_active_hazard: bool = False
    peak_active_severity: HazardSeverity = HazardSeverity.NORMAL
    last_hazard_type: HazardType = HazardType.NONE


def _safe_float(val: Any) -> Optional[float]:
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


class HazardEvaluator:
    """
    Reusable, thread-safe environmental hazard evaluation service (Stage 1).

    Evaluates:
      A. Particulate pollution (PM1.0, PM2.5, PM10, AQI)
      B. Harmful gas detection (MQ-2, MQ-9, MQ-135 + TinyGasNet MC-Dropout)
      C. Environmental trends (EMA, OLS, MAD anomaly residuals + rolling window)
      D. Model uncertainty, sensor conflicts, hardware faults, and stale/missing data
    """

    def __init__(
        self,
        settings: Optional[Settings] = None,
        advisory_config: Optional[AdvisoryConfig] = None,
    ) -> None:
        cfg = settings or get_settings()
        self.standard = cfg.HAZARD_AQI_STANDARD
        self.advisory_cfg = advisory_config or AdvisoryConfig.for_standard(
            self.standard
        )
        self.uncertainty_threshold = cfg.HAZARD_UNCERTAINTY_THRESHOLD
        self.min_class_confidence = cfg.HAZARD_MIN_CLASS_CONFIDENCE
        self.stale_data_seconds = cfg.HAZARD_STALE_DATA_SECONDS
        self.sudden_pm25_delta = cfg.HAZARD_SUDDEN_PM25_DELTA_UGM3
        self.sudden_pm10_delta = cfg.HAZARD_SUDDEN_PM10_DELTA_UGM3
        self.sudden_mq_delta_v = cfg.HAZARD_SUDDEN_MQ_DELTA_V
        self.persistent_min_readings = cfg.HAZARD_PERSISTENT_MIN_READINGS
        self.recovery_min_readings = cfg.HAZARD_RECOVERY_MIN_READINGS

        self._node_states: Dict[str, _NodeEvaluationHistory] = {}
        self._lock = threading.RLock()

    def reset_node(self, node_id: str) -> None:
        """Reset rolling evaluation state for a specific node."""
        with self._lock:
            self._node_states.pop(node_id, None)

    def _get_node_state(self, node_id: str) -> _NodeEvaluationHistory:
        with self._lock:
            if node_id not in self._node_states:
                self._node_states[node_id] = _NodeEvaluationHistory()
            return self._node_states[node_id]

    # ------------------------------------------------------------------
    # Public Evaluation Entry Point
    # ------------------------------------------------------------------

    def evaluate(
        self,
        payload: Union[SensorPayload, Dict[str, Any]],
        *,
        inference: Optional[InferenceResult] = None,
        anomaly_report: Optional[Union[AnomalyReport, Dict[str, Any]]] = None,
        source_result: Optional[Dict[str, Any]] = None,
        aqi_result: Optional[Union[AQICalculationResult, Dict[str, Any]]] = None,
        pipeline_results: Optional[PipelineResults] = None,
        reference_time: Optional[datetime] = None,
    ) -> HazardEvaluationResult:
        """
        Evaluate a single sensor observation and its associated intelligence
        pipeline outputs to produce a deterministic `HazardEvaluationResult`.
        """
        extracted = self._extract_measurements(payload, aqi_result)
        node_id = extracted["node_id"]
        obs_ts = extracted["timestamp"]
        now_ref = ensure_utc(reference_time) or utc_now()
        measurements = extracted["measurements"]
        missing_fields = extracted["missing_fields"]

        # Normalize optional anomaly report
        parsed_anomaly: Optional[AnomalyReport] = None
        if isinstance(anomaly_report, AnomalyReport):
            parsed_anomaly = anomaly_report
        elif isinstance(anomaly_report, dict) and anomaly_report:
            try:
                parsed_anomaly = AnomalyReport.from_engine_dict(anomaly_report)
            except Exception:
                parsed_anomaly = None
        elif (
            pipeline_results is not None
            and pipeline_results.anomaly_report is not None
        ):
            parsed_anomaly = pipeline_results.anomaly_report

        with self._lock:
            history = self._get_node_state(node_id)
            return self._evaluate_locked(
                node_id=node_id,
                obs_ts=obs_ts,
                now_ref=now_ref,
                measurements=measurements,
                missing_fields=missing_fields,
                inference=inference,
                anomaly_report=parsed_anomaly,
                source_result=source_result,
                pipeline_results=pipeline_results,
                history=history,
            )

    # ------------------------------------------------------------------
    # Core Locked Evaluation Logic
    # ------------------------------------------------------------------

    def _evaluate_locked(
        self,
        *,
        node_id: str,
        obs_ts: datetime,
        now_ref: datetime,
        measurements: Dict[str, Optional[float]],
        missing_fields: List[str],
        inference: Optional[InferenceResult],
        anomaly_report: Optional[AnomalyReport],
        source_result: Optional[Dict[str, Any]],
        pipeline_results: Optional[PipelineResults],
        history: _NodeEvaluationHistory,
    ) -> HazardEvaluationResult:
        evidence: List[str] = []
        pm1_0 = measurements.get("PM1_0")
        pm2_5 = measurements.get("PM2_5")
        pm10 = measurements.get("PM10")
        mq2_v = measurements.get("MQ2_V")
        mq9_v = measurements.get("MQ9_V")
        mq135_v = measurements.get("MQ135_V")
        temp_c = measurements.get("temperature_C")
        hum_pct = measurements.get("humidity_pct")
        aqi_val = measurements.get("aqi")

        # 1. Check for Stale Timestamp
        age_seconds = (now_ref - obs_ts).total_seconds()
        is_stale = age_seconds > self.stale_data_seconds
        if (
            anomaly_report is not None
            and str(anomaly_report.data_quality.status).upper() == "STALE"
        ):
            is_stale = True
        if (
            pipeline_results is not None
            and str(pipeline_results.health.status).lower() == "stale"
        ):
            is_stale = True
        if is_stale:
            evidence.append(
                f"Telemetry timestamp is stale ({max(age_seconds, 0.0):.0f}s old > {self.stale_data_seconds:.0f}s limit)"
            )

        # 2. Check for Missing Sensor Channels
        has_missing = bool(missing_fields)
        if (
            anomaly_report is not None
            and anomaly_report.data_quality.missing_features
        ):
            for mf in anomaly_report.data_quality.missing_features:
                if mf not in missing_fields:
                    missing_fields.append(mf)
            has_missing = True
        if has_missing:
            evidence.append(
                f"Missing sensor measurements: {', '.join(missing_fields)}"
            )

        # 3. Check Pre-Inference Electrical & Physical Safety Gate
        gate_res = SensorSafetyGate.validate(
            mq2_v=mq2_v,
            mq9_v=mq9_v,
            mq135_v=mq135_v,
            temperature_c=temp_c,
            humidity_pct=hum_pct,
        )
        non_missing_violations = [
            v for v in gate_res.violations if "is missing (null/None)" not in v
        ]
        has_hw_fault = bool(
            (bool(non_missing_violations) and gate_res.has_hardware_fault)
            or (
                inference is not None
                and inference.status == InferenceStatus.SENSOR_FAULT
            )
            or (
                anomaly_report is not None
                and anomaly_report.is_hardware_fault
            )
        )
        if non_missing_violations:
            for v_msg in non_missing_violations:
                evidence.append(f"SafetyGate violation: {v_msg}")

        if anomaly_report is not None and anomaly_report.is_hardware_fault:
            evidence.append(
                f"AnomalyEngine hardware fault detected: {anomaly_report.anomaly_source_detail or anomaly_report.anomaly_source}"
            )

        # 4. Check for Conflicting Sensor Measurements
        has_conflict, conflict_reasons = self._detect_sensor_conflicts(
            pm1_0=pm1_0,
            pm2_5=pm2_5,
            pm10=pm10,
            mq2_v=mq2_v,
            mq9_v=mq9_v,
            mq135_v=mq135_v,
            inference=inference,
        )
        if has_conflict:
            evidence.extend(conflict_reasons)

        # 5. Extract Model Confidence & Uncertainty (MC-Dropout & SourceClassifier)
        model_confidence: Optional[float] = None
        model_uncertainty: Optional[float] = None
        is_uncertain = False

        if inference is not None:
            model_confidence = inference.class_confidence
            model_uncertainty = inference.uncertainty
            if (
                inference.status in (InferenceStatus.ABSTAIN, InferenceStatus.SENSOR_FAULT)
                or (
                    inference.uncertainty is not None
                    and inference.uncertainty > self.uncertainty_threshold
                )
            ):
                is_uncertain = True
                evidence.append(
                    f"TinyGasNet MC-Dropout uncertainty is elevated "
                    f"(uncertainty={inference.uncertainty}, status={inference.status.value})"
                )
            elif (
                inference.status == InferenceStatus.SUCCESS
                and inference.class_confidence is not None
                and inference.class_confidence < self.min_class_confidence
                and inference.gas_class not in (None, "CleanAir")
            ):
                is_uncertain = True
                evidence.append(
                    f"TinyGasNet class confidence ({inference.class_confidence:.2f}) "
                    f"is below minimum threshold ({self.min_class_confidence:.2f})"
                )

        pollution_source_candidate: Optional[str] = None
        if source_result is not None:
            if isinstance(source_result, dict):
                top_src = source_result.get("top_source")
                src_unc = source_result.get("uncertainty") or {}
            else:
                top_src = getattr(source_result, "top_source", None)
                src_unc = getattr(source_result, "uncertainty", None)
            if top_src and str(top_src).lower() not in ("unknown", "unavailable"):
                pollution_source_candidate = str(top_src)
            if isinstance(src_unc, dict) and src_unc.get("is_uncertain"):
                evidence.append(
                    f"SourceClassifier reported uncertainty: {src_unc.get('reason', 'ambiguous source')}"
                )
            elif src_unc is not None and getattr(src_unc, "is_uncertain", False):
                reason = getattr(src_unc, "reason", None) or "ambiguous source"
                evidence.append(f"SourceClassifier reported uncertainty: {reason}")

        # 6. Evaluate Sudden Deltas & Historical Trends (EMA, OLS, MAD)
        prev_snap = history.snapshots[-1] if history.snapshots else None
        delta_pm25 = (
            (pm2_5 - prev_snap.pm2_5)
            if (pm2_5 is not None and prev_snap and prev_snap.pm2_5 is not None)
            else 0.0
        )
        delta_pm10 = (
            (pm10 - prev_snap.pm10)
            if (pm10 is not None and prev_snap and prev_snap.pm10 is not None)
            else 0.0
        )
        delta_mq_max = 0.0
        if prev_snap is not None:
            for curr_v, old_v in (
                (mq2_v, prev_snap.mq2_v),
                (mq9_v, prev_snap.mq9_v),
                (mq135_v, prev_snap.mq135_v),
            ):
                if curr_v is not None and old_v is not None:
                    delta_mq_max = max(delta_mq_max, curr_v - old_v)

        measurements["delta_PM2_5"] = round(delta_pm25, 2)
        measurements["delta_PM10"] = round(delta_pm10, 2)
        measurements["delta_MQ_max_V"] = round(delta_mq_max, 3)

        sudden_pm_spike = (
            delta_pm25 >= self.sudden_pm25_delta
            or delta_pm10 >= self.sudden_pm10_delta
        )
        if anomaly_report is not None and anomaly_report.is_environmental_event:
            for pm_feat in ("PM2_5", "PM10"):
                ev = anomaly_report.sensor_evidence.get(pm_feat)
                if ev is not None and ev.score >= 3.0 and (ev.residual or 0.0) > 0:
                    sudden_pm_spike = True
                    evidence.append(
                        f"MAD/OLS anomaly spike on {pm_feat}: actual={ev.actual}, "
                        f"expected={ev.expected}, score={ev.score:.2f}"
                    )

        if delta_pm25 >= self.sudden_pm25_delta:
            evidence.append(
                f"Sudden PM2.5 increase detected (+{delta_pm25:.1f} µg/m³ >= {self.sudden_pm25_delta:.1f} µg/m³)"
            )
        if delta_pm10 >= self.sudden_pm10_delta:
            evidence.append(
                f"Sudden PM10 increase detected (+{delta_pm10:.1f} µg/m³ >= {self.sudden_pm10_delta:.1f} µg/m³)"
            )

        # 7. Evaluate Particulate Severity (if valid & not conflicted)
        pm_severity, pm_reasons = self._evaluate_particulate_severity(
            pm1_0=pm1_0,
            pm2_5=pm2_5,
            pm10=pm10,
            aqi_val=aqi_val,
            sudden_pm_spike=sudden_pm_spike,
            has_conflict=has_conflict,
        )
        evidence.extend(pm_reasons)

        # 8. Evaluate Harmful Gas Severity & Honest Gas Identity Candidate
        gas_severity, gas_identity, gas_reasons = self._evaluate_gas_hazard(
            mq2_v=mq2_v,
            mq9_v=mq9_v,
            mq135_v=mq135_v,
            delta_mq_max=delta_mq_max,
            inference=inference,
            is_uncertain=is_uncertain,
            has_hw_fault=has_hw_fault,
            has_conflict=has_conflict,
        )
        evidence.extend(gas_reasons)

        # 9. Determine Primary HazardType, Rolling Persistence & Final Severity
        raw_hazard_active = (
            SEVERITY_RANK[pm_severity] >= SEVERITY_RANK[HazardSeverity.WARNING]
            or SEVERITY_RANK[gas_severity] >= SEVERITY_RANK[HazardSeverity.WARNING]
        ) and not (has_hw_fault or is_stale or has_missing or has_conflict)

        if raw_hazard_active:
            history.consecutive_hazard_count += 1
            history.consecutive_recovery_count = 0
            if (
                SEVERITY_RANK[pm_severity] >= SEVERITY_RANK[HazardSeverity.CRITICAL]
                or SEVERITY_RANK[gas_severity] >= SEVERITY_RANK[HazardSeverity.CRITICAL]
            ):
                history.consecutive_critical_count += 1
            else:
                history.consecutive_critical_count = 0
        else:
            if history.had_active_hazard and not (
                has_hw_fault or is_stale or has_missing or has_conflict
            ):
                history.consecutive_recovery_count += 1
            history.consecutive_hazard_count = 0
            history.consecutive_critical_count = 0

        is_persistent = (
            history.consecutive_hazard_count >= self.persistent_min_readings
        )
        if is_persistent:
            evidence.append(
                f"Persistent hazard condition across {history.consecutive_hazard_count} consecutive readings"
            )

        # Select final classification and severity
        hazard_type, final_severity, reason = self._synthesize_decision(
            pm_severity=pm_severity,
            gas_severity=gas_severity,
            sudden_pm_spike=sudden_pm_spike,
            is_persistent=is_persistent,
            is_uncertain=is_uncertain,
            has_conflict=has_conflict,
            has_missing=has_missing,
            is_stale=is_stale,
            has_hw_fault=has_hw_fault,
            anomaly_report=anomaly_report,
            history=history,
            gas_identity=gas_identity,
        )

        # Determine environmental trend
        env_trend = self._determine_environmental_trend(
            hazard_type=hazard_type,
            final_severity=final_severity,
            sudden_pm_spike=sudden_pm_spike,
            delta_mq_max=delta_mq_max,
            is_persistent=is_persistent,
            has_missing=has_missing,
            is_stale=is_stale,
            anomaly_report=anomaly_report,
            history=history,
            pm2_5=pm2_5,
        )

        # Update history state for subsequent readings
        if SEVERITY_RANK[final_severity] >= SEVERITY_RANK[HazardSeverity.WARNING] and hazard_type not in (
            HazardType.MISSING_OR_STALE_DATA,
            HazardType.SENSOR_ANOMALY_OR_FAULT,
            HazardType.ENVIRONMENTAL_RECOVERY,
        ):
            history.had_active_hazard = True
            if SEVERITY_RANK[final_severity] > SEVERITY_RANK[history.peak_active_severity]:
                history.peak_active_severity = final_severity
            history.last_hazard_type = hazard_type
        elif hazard_type == HazardType.NONE and history.consecutive_recovery_count >= self.recovery_min_readings:
            history.had_active_hazard = False
            history.peak_active_severity = HazardSeverity.NORMAL
            history.last_hazard_type = HazardType.NONE

        history.snapshots.append(
            _ObservationSnapshot(
                timestamp=obs_ts,
                pm1_0=pm1_0,
                pm2_5=pm2_5,
                pm10=pm10,
                mq2_v=mq2_v,
                mq9_v=mq9_v,
                mq135_v=mq135_v,
                temperature_c=temp_c,
                humidity_pct=hum_pct,
                severity=final_severity,
                hazard_type=hazard_type,
            )
        )

        return HazardEvaluationResult(
            node_id=node_id,
            detection_timestamp=obs_ts,
            hazard_type=hazard_type,
            severity=final_severity,
            environmental_trend=env_trend,
            relevant_measurements=measurements,
            supporting_evidence=evidence,
            gas_identity_candidate=gas_identity,
            pollution_source_candidate=pollution_source_candidate,
            model_confidence=model_confidence,
            model_uncertainty=model_uncertainty,
            is_uncertain=is_uncertain,
            has_sensor_conflict=has_conflict,
            has_missing_data=has_missing,
            is_stale_data=is_stale,
            has_hardware_fault=has_hw_fault,
            consecutive_hazard_count=history.consecutive_hazard_count,
            consecutive_recovery_count=history.consecutive_recovery_count,
            reason=reason,
        )

    # ------------------------------------------------------------------
    # Sub-Evaluators
    # ------------------------------------------------------------------

    def _extract_measurements(
        self,
        payload: Union[SensorPayload, Dict[str, Any]],
        aqi_result: Optional[Union[AQICalculationResult, Dict[str, Any]]],
    ) -> Dict[str, Any]:
        missing_fields: List[str] = []

        if isinstance(payload, SensorPayload):
            node_id = payload.node_id
            ts = ensure_utc(payload.timestamp) or utc_now()
            pm1_0: Optional[float] = float(payload.particulate_matter.PM1_0)
            pm2_5: Optional[float] = float(payload.particulate_matter.PM2_5)
            pm10: Optional[float] = float(payload.particulate_matter.PM10)
            mq2_v: Optional[float] = float(payload.gas_sensors.MQ2.voltage_V)
            mq9_v: Optional[float] = float(payload.gas_sensors.MQ9.voltage_V)
            mq135_v: Optional[float] = float(payload.gas_sensors.MQ135.voltage_V)
            temp_c: Optional[float] = float(payload.environment.temperature_C)
            hum_pct: Optional[float] = float(payload.environment.humidity_pct)
        elif isinstance(payload, dict):
            node_id = str(payload.get("node_id") or "unknown-node")
            raw_ts = payload.get("timestamp")
            if isinstance(raw_ts, datetime):
                ts = ensure_utc(raw_ts) or utc_now()
            elif isinstance(raw_ts, str):
                try:
                    ts = ensure_utc(datetime.fromisoformat(raw_ts)) or utc_now()
                except ValueError:
                    ts = utc_now()
            else:
                ts = utc_now()

            env = payload.get("environment") or {}
            pm = payload.get("particulate_matter") or payload.get("pm") or {}
            gas = payload.get("gas_sensors") or {}

            def _get_gas_v(key: str) -> Optional[float]:
                g_obj = gas.get(key)
                if isinstance(g_obj, dict):
                    return _safe_float(g_obj.get("voltage_V"))
                return _safe_float(
                    gas.get(f"{key}_V")
                    or payload.get(f"{key.lower()}_v")
                    or payload.get(f"{key}_V")
                )

            pm1_0 = _safe_float(pm.get("PM1_0") if "PM1_0" in pm else payload.get("PM1_0"))
            pm2_5 = _safe_float(pm.get("PM2_5") if "PM2_5" in pm else payload.get("PM2_5"))
            pm10 = _safe_float(pm.get("PM10") if "PM10" in pm else payload.get("PM10"))
            mq2_v = _get_gas_v("MQ2")
            mq9_v = _get_gas_v("MQ9")
            mq135_v = _get_gas_v("MQ135")
            temp_c = _safe_float(
                env.get("temperature_C")
                if "temperature_C" in env
                else payload.get("temperature_C")
            )
            hum_pct = _safe_float(
                env.get("humidity_pct")
                if "humidity_pct" in env
                else payload.get("humidity_pct")
            )
        else:
            raise TypeError(f"Unsupported payload type: {type(payload)}")

        aqi_val: Optional[float] = None
        if isinstance(aqi_result, AQICalculationResult):
            aqi_val = aqi_result.aqi
        elif isinstance(aqi_result, dict):
            aqi_val = _safe_float(aqi_result.get("aqi"))
        elif isinstance(payload, dict) and "aqi" in payload:
            aqi_val = _safe_float(payload.get("aqi"))

        channel_map = {
            "PM1_0": pm1_0,
            "PM2_5": pm2_5,
            "PM10": pm10,
            "MQ2_V": mq2_v,
            "MQ9_V": mq9_v,
            "MQ135_V": mq135_v,
            "temperature_C": temp_c,
            "humidity_pct": hum_pct,
        }
        for k, v in channel_map.items():
            if v is None:
                missing_fields.append(k)

        channel_map["aqi"] = aqi_val
        return {
            "node_id": node_id,
            "timestamp": ts,
            "measurements": channel_map,
            "missing_fields": missing_fields,
        }

    def _detect_sensor_conflicts(
        self,
        *,
        pm1_0: Optional[float],
        pm2_5: Optional[float],
        pm10: Optional[float],
        mq2_v: Optional[float],
        mq9_v: Optional[float],
        mq135_v: Optional[float],
        inference: Optional[InferenceResult],
    ) -> Tuple[bool, List[str]]:
        reasons: List[str] = []

        # 1. Physical particulate size fraction ordering conflict: PM1.0 <= PM2.5 <= PM10
        if pm1_0 is not None and pm2_5 is not None and pm1_0 > pm2_5 + 0.5:
            reasons.append(
                f"Conflicting particulate readings: PM1.0 ({pm1_0:.1f} µg/m³) exceeds PM2.5 ({pm2_5:.1f} µg/m³)"
            )
        if pm2_5 is not None and pm10 is not None and pm2_5 > pm10 + 0.5:
            reasons.append(
                f"Conflicting particulate readings: PM2.5 ({pm2_5:.1f} µg/m³) exceeds PM10 ({pm10:.1f} µg/m³)"
            )

        # 2. Cross-modal conflict: Model predicts combustion "Smoke" with high confidence,
        # yet optical PM2.5/PM10 are near zero (< 5 µg/m³) and all MQ voltages are at clean-air baseline (< 1.25V)
        if (
            inference is not None
            and inference.status == InferenceStatus.SUCCESS
            and inference.gas_class == "Smoke"
            and pm2_5 is not None
            and pm10 is not None
            and mq2_v is not None
            and mq9_v is not None
            and mq135_v is not None
        ):
            if (
                pm2_5 < 5.0
                and pm10 < 10.0
                and max(mq2_v, mq9_v, mq135_v) < 1.25
            ):
                reasons.append(
                    "Cross-sensor conflict: GasNet predicted 'Smoke' while particulate "
                    f"(PM2.5={pm2_5:.1f} µg/m³) and all MQ voltages (max={max(mq2_v, mq9_v, mq135_v):.2f}V) "
                    "are at clean-air baseline"
                )

        # 3. Severe particulate vs gas contradiction when gas model reports CleanAir with high confidence
        # while one MQ channel reports extreme voltage (> 3.4V) and the cross-sensitive pair stays at floor (< 0.45V)
        if mq2_v is not None and mq9_v is not None and mq135_v is not None:
            max_mq = max(mq2_v, mq9_v, mq135_v)
            min_mq = min(mq2_v, mq9_v, mq135_v)
            if (
                max_mq >= self.advisory_cfg.mq2_critical
                and min_mq < 0.40
                and pm2_5 is not None
                and pm2_5 < 8.0
                and inference is not None
                and inference.gas_class == "CleanAir"
            ):
                reasons.append(
                    f"Conflicting gas/particulate telemetry: isolated MQ spike ({max_mq:.2f}V) "
                    f"contradicts CleanAir inference and low PM2.5 ({pm2_5:.1f} µg/m³)"
                )

        return (len(reasons) > 0, reasons)

    def _evaluate_particulate_severity(
        self,
        *,
        pm1_0: Optional[float],
        pm2_5: Optional[float],
        pm10: Optional[float],
        aqi_val: Optional[float],
        sudden_pm_spike: bool,
        has_conflict: bool,
    ) -> Tuple[HazardSeverity, List[str]]:
        if has_conflict:
            return HazardSeverity.WARNING, []

        reasons: List[str] = []
        cfg = self.advisory_cfg
        sev = HazardSeverity.NORMAL

        # Check critical thresholds (derived from AdvisoryConfig)
        if (
            (pm2_5 is not None and pm2_5 >= cfg.pm25_critical)
            or (pm10 is not None and pm10 >= cfg.pm10_critical)
            or (aqi_val is not None and aqi_val >= cfg.aqi_critical)
        ):
            sev = HazardSeverity.CRITICAL
            reasons.append(
                f"Critical particulate concentration (PM2.5={pm2_5}, PM10={pm10}, AQI={aqi_val})"
            )
        elif (
            (pm2_5 is not None and pm2_5 >= cfg.pm25_severe)
            or (pm10 is not None and pm10 >= cfg.pm10_severe)
            or (aqi_val is not None and aqi_val >= cfg.aqi_severe)
        ):
            sev = HazardSeverity.CRITICAL
            reasons.append(
                f"Severe particulate pollution (PM2.5={pm2_5}, PM10={pm10}, AQI={aqi_val})"
            )
        elif (
            (pm2_5 is not None and pm2_5 >= cfg.pm25_moderate)
            or (pm10 is not None and pm10 >= cfg.pm10_moderate)
            or (aqi_val is not None and aqi_val >= cfg.aqi_moderate)
        ):
            sev = HazardSeverity.WARNING
            reasons.append(
                f"Elevated particulate concentration (PM2.5={pm2_5}, PM10={pm10}, AQI={aqi_val})"
            )
        elif sudden_pm_spike:
            sev = HazardSeverity.WARNING

        return sev, reasons

    def _evaluate_gas_hazard(
        self,
        *,
        mq2_v: Optional[float],
        mq9_v: Optional[float],
        mq135_v: Optional[float],
        delta_mq_max: float,
        inference: Optional[InferenceResult],
        is_uncertain: bool,
        has_hw_fault: bool,
        has_conflict: bool,
    ) -> Tuple[HazardSeverity, Optional[str], List[str]]:
        if has_hw_fault or has_conflict:
            return HazardSeverity.NORMAL, None, []

        cfg = self.advisory_cfg
        reasons: List[str] = []
        sev = HazardSeverity.NORMAL
        gas_identity: Optional[str] = None

        # Evaluate physical MOS voltage levels (only within valid electrical bounds [0.10V, 4.90V])
        v2 = mq2_v if (mq2_v is not None and cfg.mq_voltage_min <= mq2_v <= cfg.mq_voltage_max) else None
        v9 = mq9_v if (mq9_v is not None and cfg.mq_voltage_min <= mq9_v <= cfg.mq_voltage_max) else None
        v135 = mq135_v if (mq135_v is not None and cfg.mq_voltage_min <= mq135_v <= cfg.mq_voltage_max) else None

        if (
            (v9 is not None and v9 >= cfg.mq9_critical)
            or (v2 is not None and v2 >= cfg.mq2_critical)
            or (v135 is not None and v135 >= cfg.mq135_critical)
        ):
            sev = HazardSeverity.EMERGENCY
            reasons.append(
                f"Critical MQ gas voltage breach (MQ2={v2}V, MQ9={v9}V, MQ135={v135}V)"
            )
        elif (
            (v9 is not None and v9 >= cfg.mq9_severe)
            or (v2 is not None and v2 >= cfg.mq2_severe)
            or (v135 is not None and v135 >= cfg.mq135_severe)
        ):
            sev = HazardSeverity.CRITICAL
            reasons.append(
                f"Severe MQ gas voltage elevation (MQ2={v2}V, MQ9={v9}V, MQ135={v135}V)"
            )
        elif (
            (v9 is not None and v9 >= cfg.mq9_moderate)
            or (v2 is not None and v2 >= cfg.mq2_moderate)
            or (v135 is not None and v135 >= cfg.mq135_moderate)
            or delta_mq_max >= self.sudden_mq_delta_v
        ):
            sev = HazardSeverity.WARNING
            reasons.append(
                f"Elevated MQ gas sensor response (MQ2={v2}V, MQ9={v9}V, MQ135={v135}V, delta={delta_mq_max:.2f}V)"
            )

        # Evaluate TinyGasNet neural inference without claiming exact chemical speciation
        # when the model is unconfigured, uncertain, or low-confidence.
        if (
            inference is not None
            and inference.status == InferenceStatus.SUCCESS
            and not is_uncertain
        ):
            g_cls = (inference.gas_class or "").strip()
            s_stat = (inference.safety_status or "").strip().lower()
            s_conf = inference.safety_confidence or 0.0
            c_conf = inference.class_confidence or 0.0

            if g_cls in ("CO", "LPG", "Smoke", "Alcohol") and c_conf >= self.min_class_confidence:
                gas_identity = g_cls
                reasons.append(
                    f"TinyGasNet classified gas pattern '{g_cls}' "
                    f"(confidence={c_conf:.2f}, uncertainty={inference.uncertainty})"
                )
                if s_stat in ("unsafe", "hazardous") and s_conf >= self.min_class_confidence:
                    if SEVERITY_RANK[sev] < SEVERITY_RANK[HazardSeverity.CRITICAL]:
                        # Require physical MQ corroboration (>= moderate threshold) for CRITICAL
                        if any(
                            v is not None and v >= 1.80 for v in (v2, v9, v135)
                        ):
                            sev = HazardSeverity.CRITICAL
                        else:
                            sev = HazardSeverity.WARNING
            elif g_cls == "CleanAir":
                gas_identity = "CleanAir"
        else:
            if SEVERITY_RANK[sev] >= SEVERITY_RANK[HazardSeverity.WARNING]:
                # Explicitly state that MOS sensors cannot uniquely identify a specific gas without confident model support
                gas_identity = "UNESTABLISHED"
                reasons.append(
                    "Specific gas identity is UNESTABLISHED (MOS sensors respond to broad reducing/oxidizing gas families)"
                )

        return sev, gas_identity, reasons

    def _synthesize_decision(
        self,
        *,
        pm_severity: HazardSeverity,
        gas_severity: HazardSeverity,
        sudden_pm_spike: bool,
        is_persistent: bool,
        is_uncertain: bool,
        has_conflict: bool,
        has_missing: bool,
        is_stale: bool,
        has_hw_fault: bool,
        anomaly_report: Optional[AnomalyReport],
        history: _NodeEvaluationHistory,
        gas_identity: Optional[str],
    ) -> Tuple[HazardType, HazardSeverity, str]:
        # 1. Hardware fault or sensor anomaly fault
        if has_hw_fault:
            return (
                HazardType.SENSOR_ANOMALY_OR_FAULT,
                HazardSeverity.WARNING,
                "Sensor hardware or electrical bounds fault detected; physical hazard escalation inhibited.",
            )

        # 2. Missing or stale telemetry
        if has_missing or is_stale:
            detail = "stale timestamp" if is_stale else "missing sensor channels"
            return (
                HazardType.MISSING_OR_STALE_DATA,
                HazardSeverity.WARNING,
                f"Incomplete or outdated sensor telemetry ({detail}); conservative monitoring required.",
            )

        # 3. Conflicting sensor readings
        if has_conflict:
            return (
                HazardType.CONFLICTING_READINGS,
                HazardSeverity.WARNING,
                "Conflicting measurements across sensor channels; conservative warning issued pending verification.",
            )

        # 4. Combined Gas + Particulate hazard
        if (
            SEVERITY_RANK[gas_severity] >= SEVERITY_RANK[HazardSeverity.WARNING]
            and SEVERITY_RANK[pm_severity] >= SEVERITY_RANK[HazardSeverity.WARNING]
        ):
            combined_sev = max(
                gas_severity, pm_severity, key=lambda s: SEVERITY_RANK[s]
            )
            if (
                is_persistent
                and SEVERITY_RANK[combined_sev] >= SEVERITY_RANK[HazardSeverity.CRITICAL]
                and not is_uncertain
            ):
                combined_sev = HazardSeverity.EMERGENCY
            return (
                HazardType.COMBINED_GAS_AND_PARTICULATE,
                combined_sev,
                f"Co-occurring gas ({gas_identity or 'elevated MOS'}) and particulate hazard detected.",
            )

        # 5. Gas-dominant hazard
        if SEVERITY_RANK[gas_severity] >= SEVERITY_RANK[HazardSeverity.WARNING]:
            eff_gas_sev = gas_severity
            if is_uncertain and SEVERITY_RANK[eff_gas_sev] >= SEVERITY_RANK[HazardSeverity.EMERGENCY]:
                # Uncertain model predictions must not independently trigger uncorroborated emergencies
                eff_gas_sev = HazardSeverity.CRITICAL
            elif (
                is_persistent
                and SEVERITY_RANK[eff_gas_sev] >= SEVERITY_RANK[HazardSeverity.CRITICAL]
                and not is_uncertain
            ):
                eff_gas_sev = HazardSeverity.EMERGENCY

            h_type = (
                HazardType.GAS_HAZARD
                if SEVERITY_RANK[eff_gas_sev] >= SEVERITY_RANK[HazardSeverity.CRITICAL]
                else HazardType.GAS_ELEVATED
            )
            return (
                h_type,
                eff_gas_sev,
                f"Harmful gas condition ({h_type.value}, candidate={gas_identity or 'UNESTABLISHED'}) detected.",
            )

        # 6. Particulate-dominant hazard
        if SEVERITY_RANK[pm_severity] >= SEVERITY_RANK[HazardSeverity.WARNING]:
            eff_pm_sev = pm_severity
            if is_persistent:
                if SEVERITY_RANK[eff_pm_sev] >= SEVERITY_RANK[HazardSeverity.CRITICAL]:
                    eff_pm_sev = HazardSeverity.EMERGENCY
                else:
                    eff_pm_sev = HazardSeverity.CRITICAL
                return (
                    HazardType.PARTICULATE_PERSISTENT,
                    eff_pm_sev,
                    f"Persistent particulate pollution across {history.consecutive_hazard_count} readings.",
                )
            if SEVERITY_RANK[eff_pm_sev] >= SEVERITY_RANK[HazardSeverity.CRITICAL]:
                return (
                    HazardType.PARTICULATE_CRITICAL,
                    eff_pm_sev,
                    "Critical particulate matter concentration detected.",
                )
            if sudden_pm_spike:
                return (
                    HazardType.PARTICULATE_SUDDEN_INCREASE,
                    HazardSeverity.WARNING,
                    "Sudden particulate matter spike detected.",
                )
            return (
                HazardType.PARTICULATE_ELEVATED,
                HazardSeverity.WARNING,
                "Elevated particulate matter levels detected.",
            )

        # 7. Uncertain model prediction when raw values are near boundary
        if is_uncertain:
            return (
                HazardType.UNCERTAIN_PREDICTION,
                HazardSeverity.WARNING,
                "Model prediction uncertainty exceeds threshold; treated conservatively as a warning, not a confirmed emergency.",
            )

        # 8. Statistical Anomaly from AnomalyEngine (EMA/OLS/MAD) without threshold breach
        if (
            anomaly_report is not None
            and anomaly_report.anomaly.detected
            and anomaly_report.is_environmental_event
        ):
            return (
                HazardType.SENSOR_ANOMALY_OR_FAULT,
                HazardSeverity.WARNING,
                f"Statistical environmental anomaly detected by EMA/OLS/MAD engine (score={anomaly_report.anomaly.score:.2f}).",
            )

        # 9. Environmental Recovery after an active hazard
        if (
            history.had_active_hazard
            and 0 < history.consecutive_recovery_count < self.recovery_min_readings
        ):
            return (
                HazardType.ENVIRONMENTAL_RECOVERY,
                HazardSeverity.NORMAL,
                f"Environmental readings are recovering toward baseline ({history.consecutive_recovery_count}/{self.recovery_min_readings} clear readings).",
            )

        # 10. Normal baseline
        return (
            HazardType.NONE,
            HazardSeverity.NORMAL,
            "All environmental measurements are within normal operating thresholds.",
        )

    def _determine_environmental_trend(
        self,
        *,
        hazard_type: HazardType,
        final_severity: HazardSeverity,
        sudden_pm_spike: bool,
        delta_mq_max: float,
        is_persistent: bool,
        has_missing: bool,
        is_stale: bool,
        anomaly_report: Optional[AnomalyReport],
        history: _NodeEvaluationHistory,
        pm2_5: Optional[float],
    ) -> EnvironmentalTrend:
        if has_missing or is_stale:
            return EnvironmentalTrend.INSUFFICIENT_DATA
        if is_persistent:
            return EnvironmentalTrend.PERSISTENT_HAZARD
        if (
            sudden_pm_spike
            or delta_mq_max >= self.sudden_mq_delta_v
            or (
                anomaly_report is not None
                and anomaly_report.anomaly.detected
                and anomaly_report.anomaly.score >= 3.0
            )
        ):
            return EnvironmentalTrend.SUDDEN_ANOMALY
        if (
            hazard_type == HazardType.ENVIRONMENTAL_RECOVERY
            or (
                history.had_active_hazard
                and final_severity == HazardSeverity.NORMAL
            )
        ):
            return EnvironmentalTrend.RECOVERY_TREND

        # Check gradual deterioration across the last 3 snapshots
        if len(history.snapshots) >= 2 and pm2_5 is not None:
            recent_pm = [
                s.pm2_5 for s in list(history.snapshots)[-2:] if s.pm2_5 is not None
            ]
            if len(recent_pm) == 2 and recent_pm[0] < recent_pm[1] < pm2_5 and (pm2_5 - recent_pm[0]) >= 10.0:
                return EnvironmentalTrend.GRADUAL_DETERIORATION

        if SEVERITY_RANK[final_severity] >= SEVERITY_RANK[HazardSeverity.WARNING]:
            return EnvironmentalTrend.GRADUAL_DETERIORATION

        return EnvironmentalTrend.NORMAL_FLUCTUATION
