"""
Multi-sensor fusion anomaly detector.

Orchestrates: window → baseline → prediction → residuals → per-feature scores
→ category fusion → combined anomaly decision.

The fusion logic is fully deterministic and explainable.
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

from app.anomaly.baseline import BaselineEstimator
from app.anomaly.residuals import ResidualTracker
from app.anomaly.sensor_health import SensorHealthChecker, SensorStatus
from app.anomaly.window import Observation, RollingWindow

logger = logging.getLogger(__name__)


class SystemState(str, Enum):
    BOOTSTRAPPING = "BOOTSTRAPPING"
    CALIBRATING = "CALIBRATING"
    LEARNING = "LEARNING"
    MONITORING = "MONITORING"
    DEGRADED = "DEGRADED"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    NONE = "NONE"


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# Feature categories for multi-sensor fusion
PARTICULATE_FEATURES = ["PM10", "PM2_5", "PM1_0"]
GAS_FEATURES = [
    "MQ2_raw_adc", "MQ2_voltage_V",
    "MQ9_raw_adc", "MQ9_voltage_V",
    "MQ135_raw_adc", "MQ135_voltage_V",
]
ENVIRONMENTAL_FEATURES = ["temperature_C", "humidity_pct"]

ALL_FEATURES = PARTICULATE_FEATURES + GAS_FEATURES + ENVIRONMENTAL_FEATURES


class FeatureResult:
    """Result for a single analysed feature."""

    __slots__ = (
        "feature_name", "actual", "expected", "residual",
        "score", "status_label", "sensor_status", "sensor_issues",
    )

    def __init__(
        self,
        feature_name: str,
        actual: Optional[float],
        expected: Optional[float],
        residual: Optional[float],
        score: float,
        status_label: str,
        sensor_status: SensorStatus,
        sensor_issues: List[str],
    ):
        self.feature_name = feature_name
        self.actual = actual
        self.expected = expected
        self.residual = residual
        self.score = score
        self.status_label = status_label
        self.sensor_status = sensor_status
        self.sensor_issues = sensor_issues


class DetectionResult:
    """Full anomaly detection result for one observation."""

    __slots__ = (
        "timestamp", "detected", "combined_score", "severity",
        "feature_results", "system_state", "confidence",
        "missing_features", "features_used", "explanations",
        "anomaly_source", "anomaly_source_detail",
        "data_status",
    )

    def __init__(self):
        self.timestamp: Optional[datetime] = None
        self.detected: bool = False
        self.combined_score: float = 0.0
        self.severity: Severity = Severity.NONE
        self.feature_results: Dict[str, FeatureResult] = {}
        self.system_state: SystemState = SystemState.BOOTSTRAPPING
        self.confidence: Confidence = Confidence.INSUFFICIENT_DATA
        self.missing_features: List[str] = []
        self.features_used: List[str] = []
        self.explanations: List[str] = []
        self.anomaly_source: str = "UNKNOWN"
        self.anomaly_source_detail: str = ""
        self.data_status: str = "OK"  # OK, PARTIAL_DATA, STALE, INSUFFICIENT_DATA

    def to_dict(self) -> dict:
        """Serialise to a plain dictionary for JSON output."""
        sensor_evidence = {}
        for fname, fr in self.feature_results.items():
            sensor_evidence[fname] = {
                "actual": fr.actual,
                "expected": fr.expected,
                "residual": fr.residual,
                "score": round(fr.score, 3),
                "status": fr.status_label,
                "sensor_health": fr.sensor_status.value,
            }

        return {
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "anomaly": {
                "detected": self.detected,
                "score": round(self.combined_score, 3),
                "severity": self.severity.value,
            },
            "sensor_evidence": sensor_evidence,
            "data_quality": {
                "status": self.data_status,
                "missing_features": self.missing_features,
                "features_used": self.features_used,
                "sensor_health": "GOOD"
                if not self.missing_features
                else "PARTIAL",
                "confidence": self.confidence.value,
            },
            "system_state": self.system_state.value,
            "anomaly_source": self.anomaly_source,
            "anomaly_source_detail": self.anomaly_source_detail,
            "explanations": self.explanations,
        }


class AnomalyDetector:
    """
    Multi-sensor fusion anomaly detector.

    Parameters
    ----------
    threshold_medium : float
        Score threshold for MEDIUM severity.
    threshold_high : float
        Score threshold for HIGH severity.
    bootstrap_samples : int
        Observations required before any anomaly reporting.
    min_samples_monitoring : int
        Observations required for Level 1 baseline.
    min_samples_regression : int
        Observations required for Level 2 regression.
    """

    def __init__(
        self,
        threshold_medium: float = 2.0,
        threshold_high: float = 3.0,
        bootstrap_samples: int = 5,
        min_samples_monitoring: int = 10,
        min_samples_regression: int = 30,
    ):
        self.threshold_medium = threshold_medium
        self.threshold_high = threshold_high
        self.bootstrap_samples = bootstrap_samples
        self.min_samples_monitoring = min_samples_monitoring
        self.min_samples_regression = min_samples_regression

        self.baseline = BaselineEstimator(
            min_samples_regression=min_samples_regression,
            min_samples_monitoring=min_samples_monitoring,
        )
        self.residuals = ResidualTracker()
        self.health_checker = SensorHealthChecker()
        self.observation_count: int = 0

    # ------------------------------------------------------------------
    # Core analysis
    # ------------------------------------------------------------------

    def detect(
        self,
        observation: Observation,
        window: RollingWindow,
    ) -> DetectionResult:
        """
        Run the full detection pipeline for a single observation.
        """
        result = DetectionResult()
        result.timestamp = observation.timestamp
        self.observation_count = window.count()

        # --- Determine system state ---
        result.system_state = self._determine_state(window)

        # --- Analyse each feature ---
        feature_scores: Dict[str, float] = {}
        feature_statuses: Dict[str, SensorStatus] = {}
        available_features: List[str] = []
        missing_features: List[str] = []

        for feature_name in ALL_FEATURES:
            actual = observation.features.get(feature_name)

            # Get recent values for health checking
            recent_vals = window.get_values(feature_name)
            prev_val = recent_vals[-1] if recent_vals else None

            # Sensor health check
            sensor_status, sensor_issues = self.health_checker.check_feature(
                feature_name, actual, recent_vals, prev_val
            )
            feature_statuses[feature_name] = sensor_status

            if actual is None or sensor_status == SensorStatus.MISSING:
                missing_features.append(feature_name)
                result.feature_results[feature_name] = FeatureResult(
                    feature_name=feature_name,
                    actual=None,
                    expected=None,
                    residual=None,
                    score=0.0,
                    status_label="UNAVAILABLE",
                    sensor_status=SensorStatus.MISSING,
                    sensor_issues=sensor_issues,
                )
                continue

            if sensor_status == SensorStatus.FAILED:
                missing_features.append(feature_name)
                result.feature_results[feature_name] = FeatureResult(
                    feature_name=feature_name,
                    actual=actual,
                    expected=None,
                    residual=None,
                    score=0.0,
                    status_label="SENSOR_FAILED",
                    sensor_status=sensor_status,
                    sensor_issues=sensor_issues,
                )
                continue

            available_features.append(feature_name)

            # --- Prediction ---
            ts_list = [ts for ts, _ in window.get_time_series(feature_name)]
            val_list = window.get_values(feature_name)

            expected = self.baseline.predict(
                feature_name,
                observation.timestamp,
                recent_values=val_list[-10:] if val_list else None,
                recent_timestamps=ts_list[-10:] if ts_list else None,
            )

            if expected is None:
                # No baseline yet
                result.feature_results[feature_name] = FeatureResult(
                    feature_name=feature_name,
                    actual=actual,
                    expected=None,
                    residual=None,
                    score=0.0,
                    status_label="NO_BASELINE",
                    sensor_status=sensor_status,
                    sensor_issues=sensor_issues,
                )
                continue

            # --- Residual ---
            residual = actual - expected
            min_floor = BaselineEstimator.get_min_deviation_floor(feature_name)
            self.residuals.record_residual(feature_name, residual)
            score = self.residuals.compute_score(feature_name, residual, min_floor)

            feature_scores[feature_name] = score

            # Classify individual feature status
            if score >= self.threshold_high:
                status_label = "ANOMALOUS"
            elif score >= self.threshold_medium:
                status_label = "ELEVATED"
            else:
                status_label = "NORMAL"

            result.feature_results[feature_name] = FeatureResult(
                feature_name=feature_name,
                actual=actual,
                expected=round(expected, 4),
                residual=round(residual, 4),
                score=round(score, 3),
                status_label=status_label,
                sensor_status=sensor_status,
                sensor_issues=sensor_issues,
            )

        result.missing_features = missing_features
        result.features_used = available_features

        # --- Data status ---
        if not available_features:
            result.data_status = "INSUFFICIENT_DATA"
        elif missing_features:
            result.data_status = "PARTIAL_DATA"
        else:
            result.data_status = "OK"

        # --- Skip scoring during bootstrap ---
        if result.system_state == SystemState.BOOTSTRAPPING:
            result.detected = False
            result.combined_score = 0.0
            result.severity = Severity.NONE
            result.confidence = Confidence.INSUFFICIENT_DATA
            result.explanations = ["System is bootstrapping — collecting baseline data"]
            return result

        # --- Multi-sensor fusion ---
        if feature_scores:
            result.combined_score = self._fuse_scores(feature_scores)
        else:
            result.combined_score = 0.0

        # --- Severity ---
        if result.combined_score >= self.threshold_high:
            result.severity = Severity.HIGH
            result.detected = True
        elif result.combined_score >= self.threshold_medium:
            result.severity = Severity.MEDIUM
            result.detected = True
        else:
            result.severity = Severity.LOW
            result.detected = False

        # --- Classify anomaly source ---
        if result.detected:
            source, detail = self.health_checker.classify_anomaly_source(
                feature_statuses, feature_scores, self.threshold_medium
            )
            result.anomaly_source = source
            result.anomaly_source_detail = detail

        # --- Confidence ---
        result.confidence = self._estimate_confidence(
            window, available_features, missing_features, result.system_state
        )

        # --- Explanations ---
        result.explanations = self._build_explanations(result, feature_scores)

        return result

    # ------------------------------------------------------------------
    # Fusion
    # ------------------------------------------------------------------

    def _fuse_scores(self, feature_scores: Dict[str, float]) -> float:
        """
        Combine per-feature scores into a single anomaly score.

        Computes weighted category scores with a corroboration bonus
        when multiple sensor types are simultaneously elevated.
        """
        # Category scores: take the max within each category
        def _category_max(features: List[str]) -> Optional[float]:
            vals = [feature_scores[f] for f in features if f in feature_scores]
            return max(vals) if vals else None

        pm_score = _category_max(PARTICULATE_FEATURES)
        gas_score = _category_max(GAS_FEATURES)
        env_score = _category_max(ENVIRONMENTAL_FEATURES)

        scores = []
        weights = []

        if pm_score is not None:
            scores.append(pm_score)
            weights.append(1.0)
        if gas_score is not None:
            scores.append(gas_score)
            weights.append(0.8)
        if env_score is not None:
            scores.append(env_score)
            weights.append(0.5)

        if not scores:
            return 0.0

        # Weighted mean
        total_weight = sum(weights)
        combined = sum(s * w for s, w in zip(scores, weights)) / total_weight

        # Corroboration bonus: if PM and gas are both elevated, boost
        if (
            pm_score is not None
            and gas_score is not None
            and pm_score >= self.threshold_medium
            and gas_score >= self.threshold_medium
        ):
            corroboration = 0.3 * min(pm_score, gas_score)
            combined += corroboration

        return combined

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _determine_state(self, window: RollingWindow) -> SystemState:
        count = window.count()

        if count < self.bootstrap_samples:
            return SystemState.BOOTSTRAPPING

        if count < self.min_samples_monitoring:
            return SystemState.CALIBRATING

        # Check if we have regression for at least one key feature
        has_regression = any(
            self.baseline.has_regression(f) for f in ALL_FEATURES
        )

        if count < self.min_samples_regression or not has_regression:
            return SystemState.LEARNING

        # Check data freshness
        newest = window.newest()
        if newest is not None:
            age_minutes = (
                datetime.now(timezone.utc) - newest.timestamp
            ).total_seconds() / 60.0
            if age_minutes > 60:  # 1 hour stale
                return SystemState.DEGRADED

        return SystemState.MONITORING

    # ------------------------------------------------------------------
    # Confidence
    # ------------------------------------------------------------------

    def _estimate_confidence(
        self,
        window: RollingWindow,
        available: List[str],
        missing: List[str],
        state: SystemState,
    ) -> Confidence:
        total_possible = len(ALL_FEATURES)
        available_ratio = len(available) / total_possible if total_possible > 0 else 0

        if state in (SystemState.BOOTSTRAPPING,):
            return Confidence.INSUFFICIENT_DATA

        if state == SystemState.CALIBRATING:
            return Confidence.LOW

        if available_ratio < 0.3:
            return Confidence.INSUFFICIENT_DATA

        if state == SystemState.DEGRADED:
            return Confidence.LOW

        if available_ratio < 0.6 or state == SystemState.LEARNING:
            return Confidence.MEDIUM

        # Check residual history depth
        has_deep_residuals = any(
            self.residuals.residual_count(f) >= 20 for f in available
        )
        if not has_deep_residuals:
            return Confidence.MEDIUM

        return Confidence.HIGH

    # ------------------------------------------------------------------
    # Explanations
    # ------------------------------------------------------------------

    def _build_explanations(
        self,
        result: DetectionResult,
        feature_scores: Dict[str, float],
    ) -> List[str]:
        explanations: List[str] = []

        if not result.detected:
            explanations.append("No significant anomaly detected")
            if result.system_state != SystemState.MONITORING:
                explanations.append(
                    f"System state: {result.system_state.value} — "
                    f"anomaly sensitivity may be limited"
                )
            return explanations

        explanations.append("ANOMALY DETECTED")

        # Primary evidence — highest-scoring features
        scored = sorted(feature_scores.items(), key=lambda x: x[1], reverse=True)
        primary = [
            (f, s) for f, s in scored if s >= self.threshold_high
        ]
        supporting = [
            (f, s) for f, s in scored
            if self.threshold_medium <= s < self.threshold_high
        ]

        if primary:
            features_str = ", ".join(
                f"{f} (score={s:.1f})" for f, s in primary
            )
            explanations.append(f"Primary evidence: {features_str}")

        if supporting:
            features_str = ", ".join(
                f"{f} (score={s:.1f})" for f, s in supporting
            )
            explanations.append(f"Supporting evidence: {features_str}")

        explanations.append(
            f"Data quality: {len(result.features_used)}/{len(ALL_FEATURES)} "
            f"features available"
        )
        explanations.append(f"Confidence: {result.confidence.value}")

        if result.anomaly_source != "UNKNOWN":
            explanations.append(
                f"Source classification: {result.anomaly_source} — "
                f"{result.anomaly_source_detail}"
            )

        return explanations
