"""
Sensor health validation and failure detection.

Distinguishes hardware sensor failures (stuck values, impossible readings,
missing data) from genuine environmental anomalies by examining individual
channel behaviour and cross-sensor correlation.
"""

import logging
from enum import Enum
from typing import Dict, List, NamedTuple, Optional, Set, Tuple

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class SensorStatus(str, Enum):
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    FAILED = "FAILED"
    MISSING = "MISSING"


class SourceClassification(NamedTuple):
    source: str
    explanation: str
    is_hardware_fault: bool
    is_environmental_event: bool


# Mapping from feature name to physical sensor device
PHYSICAL_DEVICES: Dict[str, str] = {
    "MQ2_voltage_V": "MQ2",
    "MQ2_raw_adc": "MQ2",
    "MQ9_voltage_V": "MQ9",
    "MQ9_raw_adc": "MQ9",
    "MQ135_voltage_V": "MQ135",
    "MQ135_raw_adc": "MQ135",
    "PM1_0": "PMS",
    "PM2_5": "PMS",
    "PM10": "PMS",
    "temperature_C": "TEMP",
    "humidity_pct": "HUM",
}

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

    def __init__(self) -> None:
        self._elevation_counts: Dict[str, int] = {}

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

        # --- Railed to supply rail (hard hardware failure) ---
        railed = _RAILED_THRESHOLDS.get(feature_name)
        if railed is not None:
            lo, hi = railed
            if value <= lo:
                issues.append(
                    f"{feature_name}: railed to GND (value={value} <= {lo})"
                )
                return SensorStatus.FAILED, issues
            elif value >= hi:
                issues.append(
                    f"{feature_name}: railed to VCC (value={value} >= {hi})"
                )
                return SensorStatus.FAILED, issues

        # --- Sudden impossible jump ---
        if previous_value is not None and feature_name in _MAX_JUMP:
            jump = abs(value - previous_value)
            if jump > _MAX_JUMP[feature_name]:
                issues.append(
                    f"{feature_name}: sudden jump of {jump:.2f} "
                    f"(max expected {_MAX_JUMP[feature_name]})"
                )
                # Mark degraded, not failed
                return SensorStatus.DEGRADED, issues

        # --- Frozen sensor (checked on continuous analog channels) ---
        if feature_name.endswith("_raw_adc") or feature_name.endswith("_voltage_V"):
            if recent_values is not None and len(recent_values) >= _FROZEN_MIN_SAMPLES:
                last_n = recent_values[-_FROZEN_MIN_SAMPLES:]
                if len(set(last_n)) == 1:
                    issues.append(
                        f"{feature_name}: analog channel frozen at {last_n[0]} "
                        f"for {_FROZEN_MIN_SAMPLES} consecutive readings"
                    )
                    return SensorStatus.DEGRADED, issues

        return SensorStatus.GOOD, issues

    def classify_anomaly_source(
        self,
        feature_statuses: Dict[str, SensorStatus],
        feature_scores: Dict[str, float],
        threshold: float = 2.0,
        feature_values: Optional[Dict[str, Optional[float]]] = None,
        recent_values_map: Optional[Dict[str, List[float]]] = None,
    ) -> SourceClassification:
        """
        Distinguish sensor failure from environmental anomaly.

        Returns
        -------
        SourceClassification(source, explanation, is_hardware_fault, is_environmental_event)
        """
        hw_fault_devs: Set[str] = set()

        # 1. Hard sensor failures (railed GND/VCC, invalid range, missing)
        for f, status in feature_statuses.items():
            dev = PHYSICAL_DEVICES.get(f, f)
            if status in (SensorStatus.FAILED, SensorStatus.MISSING):
                hw_fault_devs.add(dev)

        # 2. Frozen continuous analog channels (raw_adc/voltage constant across readings with elevated residual score)
        for f, status in feature_statuses.items():
            if status == SensorStatus.DEGRADED and (f.endswith("_raw_adc") or f.endswith("_voltage_V")):
                if feature_scores.get(f, 0.0) >= 1.8:
                    dev = PHYSICAL_DEVICES.get(f, f)
                    hw_fault_devs.add(dev)

        # Preliminary multi-sensor environmental corroboration check
        pm_max_score = max([sc for f, sc in feature_scores.items() if PHYSICAL_DEVICES.get(f) == "PMS"] or [0.0])
        prelim_elevated_devs = set()
        for f, sc in feature_scores.items():
            if sc >= threshold:
                prelim_elevated_devs.add(PHYSICAL_DEVICES.get(f, f))

        has_env_corroboration = (
            len(prelim_elevated_devs) >= 2
            or (len(prelim_elevated_devs) == 1 and "PMS" in prelim_elevated_devs and pm_max_score >= 3.0)
        )

        # 3. Analog stuck sensor (elevated residual + abnormally flat variance without multi-sensor environmental corroboration)
        if not has_env_corroboration and recent_values_map is not None:
            for f, score in feature_scores.items():
                if score >= threshold and f.startswith("MQ"):
                    dev = PHYSICAL_DEVICES.get(f, f)
                    r_vals = recent_values_map.get(f, [])
                    if len(r_vals) >= 6:
                        last_n = r_vals[-6:]
                        span = max(last_n) - min(last_n)
                        var = float(np.var(last_n)) if np is not None else 0.0
                        if span < 0.04 and var < 1.5e-4:
                            hw_fault_devs.add(dev)

        # 4. Uncorroborated single-channel gas drift / fault
        gas_dev_scores = {}
        for f, sc in feature_scores.items():
            dev = PHYSICAL_DEVICES.get(f, f)
            if dev in ("MQ2", "MQ9", "MQ135"):
                gas_dev_scores[dev] = max(gas_dev_scores.get(dev, 0.0), sc)

        # Update elevation counters
        for dev in ("MQ2", "MQ9", "MQ135"):
            if gas_dev_scores.get(dev, 0.0) >= threshold:
                self._elevation_counts[dev] = self._elevation_counts.get(dev, 0) + 1
            else:
                self._elevation_counts[dev] = 0

        for gdev, gscore in gas_dev_scores.items():
            other_gas = [sc for d, sc in gas_dev_scores.items() if d != gdev]
            max_other = max(other_gas) if other_gas else 0.0
            if max_other < threshold:
                if pm_max_score < threshold and gscore >= 3.0:
                    hw_fault_devs.add(gdev)
                elif pm_max_score >= threshold:
                    elev_count = self._elevation_counts.get(gdev, 0)
                    if gscore >= 4.0 or (gscore >= 3.0 and elev_count >= 3):
                        hw_fault_devs.add(gdev)

        # Identify healthy physical devices with elevated readings
        elevated_healthy_devs = set()
        for f, sc in feature_scores.items():
            dev = PHYSICAL_DEVICES.get(f, f)
            if dev not in hw_fault_devs and sc >= threshold:
                elevated_healthy_devs.add(dev)

        has_hw = len(hw_fault_devs) > 0
        has_env = (
            len(elevated_healthy_devs) >= 2
            or (len(elevated_healthy_devs) == 1 and "PMS" in elevated_healthy_devs and pm_max_score >= 3.0)
        )

        if has_hw and has_env:
            source = "MIXED"
            expl = (
                f"Hardware fault on {', '.join(sorted(hw_fault_devs))} with concurrent "
                f"environmental elevation on {', '.join(sorted(elevated_healthy_devs))}"
            )
        elif has_hw:
            source = "SENSOR_FAULT"
            expl = f"Sensor hardware fault on {', '.join(sorted(hw_fault_devs))}"
        elif has_env:
            source = "ENVIRONMENTAL"
            expl = f"Environmental surge corroborated across {', '.join(sorted(elevated_healthy_devs))}"
        elif len(elevated_healthy_devs) == 1:
            source = "UNKNOWN"
            expl = f"Uncorroborated single device elevation ({list(elevated_healthy_devs)[0]}); ambiguous cause"
        else:
            source = "NORMAL"
            expl = "All channels within expected operating baseline"

        return SourceClassification(source, expl, has_hw, has_env)
