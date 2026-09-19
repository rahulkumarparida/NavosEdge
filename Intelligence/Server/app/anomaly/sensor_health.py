"""
Sensor health validation and failure detection.

Distinguishes hardware sensor failures (stuck values, impossible readings,
missing data) from genuine environmental anomalies by examining individual
channel behaviour and cross-sensor correlation.
"""

import logging
from enum import Enum
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class SensorStatus(str, Enum):
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    FAILED = "FAILED"
    MISSING = "MISSING"


# Valid physical ranges per feature (generous bounds)
_VALID_RANGES: Dict[str, Tuple[float, float]] = {
    "temperature_C": (-50.0, 90.0),
    "humidity_pct": (0.0, 100.0),
    "PM1_0": (0.0, 2000.0),
    "PM2_5": (0.0, 2000.0),
    "PM10": (0.0, 5000.0),
    "MQ2_raw_adc": (0.0, 1023.0),
    "MQ2_voltage_V": (0.0, 5.0),
    "MQ9_raw_adc": (0.0, 1023.0),
    "MQ9_voltage_V": (0.0, 5.0),
    "MQ135_raw_adc": (0.0, 1023.0),
    "MQ135_voltage_V": (0.0, 5.0),
}

# Railed thresholds (suspiciously close to absolute min/max)
_RAILED_THRESHOLDS: Dict[str, Tuple[float, float]] = {
    "MQ2_voltage_V": (0.01, 4.99),
    "MQ9_voltage_V": (0.01, 4.99),
    "MQ135_voltage_V": (0.01, 4.99),
    "MQ2_raw_adc": (1.0, 1022.0),
    "MQ9_raw_adc": (1.0, 1022.0),
    "MQ135_raw_adc": (1.0, 1022.0),
}

# Maximum allowed single-step jump per feature (heuristic)
_MAX_JUMP: Dict[str, float] = {
    "temperature_C": 15.0,   # 15°C in one reading
    "humidity_pct": 40.0,
    "PM10": 500.0,
    "PM2_5": 400.0,
    "PM1_0": 300.0,
    "MQ2_raw_adc": 400.0,
    "MQ9_raw_adc": 400.0,
    "MQ135_raw_adc": 400.0,
    "MQ2_voltage_V": 2.0,
    "MQ9_voltage_V": 2.0,
    "MQ135_voltage_V": 2.0,
}

# Minimum variance threshold for frozen-sensor detection
_FROZEN_VARIANCE_THRESHOLD = 1e-6
_FROZEN_MIN_SAMPLES = 5


class SensorHealthChecker:
    """
    Validates individual feature values and detects sensor faults.

    Call ``check_feature()`` for each feature to get a per-channel status.
    Call ``classify_anomaly_source()`` to distinguish sensor failure from
    an environmental event.
    """

    def check_feature(
        self,
        feature_name: str,
        value: Optional[float],
        recent_values: Optional[List[float]] = None,
        previous_value: Optional[float] = None,
    ) -> Tuple[SensorStatus, List[str]]:
        """
        Validate a single feature value.

        Returns
        -------
        status : SensorStatus
        issues : list of human-readable issue descriptions
        """
        issues: List[str] = []

        # --- Missing ---
        if value is None:
            return SensorStatus.MISSING, [f"{feature_name}: value is missing"]

        # --- Impossible range ---
        vrange = _VALID_RANGES.get(feature_name)
        if vrange is not None:
            lo, hi = vrange
            if value < lo or value > hi:
                issues.append(
                    f"{feature_name}: value {value} outside valid range [{lo}, {hi}]"
                )
                return SensorStatus.FAILED, issues

        # --- Railed ---
        railed = _RAILED_THRESHOLDS.get(feature_name)
        if railed is not None:
            lo, hi = railed
            if value <= lo or value >= hi:
                issues.append(
                    f"{feature_name}: value {value} appears railed to supply rail"
                )
                return SensorStatus.DEGRADED, issues

        # --- Sudden impossible jump ---
        if previous_value is not None and feature_name in _MAX_JUMP:
            jump = abs(value - previous_value)
            if jump > _MAX_JUMP[feature_name]:
                issues.append(
                    f"{feature_name}: sudden jump of {jump:.2f} "
                    f"(max expected {_MAX_JUMP[feature_name]})"
                )
                # This could be real or a fault — mark degraded, not failed
                return SensorStatus.DEGRADED, issues

        # --- Frozen sensor ---
        if recent_values is not None and len(recent_values) >= _FROZEN_MIN_SAMPLES:
            last_n = recent_values[-_FROZEN_MIN_SAMPLES:]
            if len(set(last_n)) == 1:
                issues.append(
                    f"{feature_name}: value frozen at {last_n[0]} "
                    f"for {_FROZEN_MIN_SAMPLES} consecutive readings"
                )
                return SensorStatus.DEGRADED, issues

        return SensorStatus.GOOD, issues

    def classify_anomaly_source(
        self,
        feature_statuses: Dict[str, SensorStatus],
        feature_scores: Dict[str, float],
        threshold: float = 2.0,
    ) -> Tuple[str, str]:
        """
        Distinguish sensor failure from environmental anomaly.

        Returns
        -------
        source : str
            "SENSOR_FAULT", "ENVIRONMENTAL", or "UNKNOWN"
        explanation : str
            Human-readable explanation.
        """
        failed = [f for f, s in feature_statuses.items() if s in (SensorStatus.FAILED, SensorStatus.MISSING)]
        degraded = [f for f, s in feature_statuses.items() if s == SensorStatus.DEGRADED]
        elevated = [f for f, sc in feature_scores.items() if sc >= threshold]

        # If a feature is elevated AND its status is FAILED/DEGRADED,
        # it's likely a sensor fault.
        elevated_and_degraded = set(elevated) & (set(failed) | set(degraded))
        elevated_and_healthy = set(elevated) - elevated_and_degraded

        if elevated_and_degraded and not elevated_and_healthy:
            return (
                "SENSOR_FAULT",
                f"Elevated readings are from degraded/failed sensors: "
                f"{', '.join(sorted(elevated_and_degraded))}",
            )

        # Multiple healthy sensors elevated simultaneously → environmental
        if len(elevated_and_healthy) >= 2:
            # Check cross-domain evidence
            pm_elevated = any(f.startswith("PM") for f in elevated_and_healthy)
            gas_elevated = any(f.startswith("MQ") for f in elevated_and_healthy)
            if pm_elevated and gas_elevated:
                return (
                    "ENVIRONMENTAL",
                    f"Corroborated by multiple sensor types: "
                    f"{', '.join(sorted(elevated_and_healthy))}",
                )
            return (
                "ENVIRONMENTAL",
                f"Multiple sensors elevated: {', '.join(sorted(elevated_and_healthy))}",
            )

        if len(elevated_and_healthy) == 1:
            return (
                "UNKNOWN",
                f"Only one sensor elevated ({list(elevated_and_healthy)[0]}); "
                f"cannot distinguish sensor fault from environmental event",
            )

        return (
            "UNKNOWN",
            "No significantly elevated features detected",
        )
