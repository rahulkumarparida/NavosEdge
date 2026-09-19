"""
Top-level anomaly engine — the service interface.

Manages per-node state, loads history from JSONL storage, maintains rolling
windows, periodically refits baselines, and exposes a single ``analyse()``
entry point that produces a structured anomaly report.

Thread-safe for use from an async FastAPI context via ``run_in_executor``.
"""

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from app.anomaly.baseline import BaselineEstimator
from app.anomaly.detector import (
    ALL_FEATURES,
    AnomalyDetector,
    DetectionResult,
    SystemState,
)
from app.anomaly.residuals import ResidualTracker
from app.anomaly.temporal import extract_temporal_features
from app.anomaly.window import Observation, RollingWindow

logger = logging.getLogger(__name__)

# Canonical feature name extraction from a stored JSONL record
_FEATURE_MAP = {
    "temperature_C":  ("environment", "temperature_C"),
    "humidity_pct":    ("environment", "humidity_pct"),
    "PM1_0":          ("particulate_matter", "PM1_0"),
    "PM2_5":          ("particulate_matter", "PM2_5"),
    "PM10":           ("particulate_matter", "PM10"),
    "MQ2_raw_adc":    ("gas_sensors", "MQ2", "raw_adc"),
    "MQ2_voltage_V":  ("gas_sensors", "MQ2", "voltage_V"),
    "MQ9_raw_adc":    ("gas_sensors", "MQ9", "raw_adc"),
    "MQ9_voltage_V":  ("gas_sensors", "MQ9", "voltage_V"),
    "MQ135_raw_adc":  ("gas_sensors", "MQ135", "raw_adc"),
    "MQ135_voltage_V":("gas_sensors", "MQ135", "voltage_V"),
}


def extract_features_from_record(record: dict) -> Dict[str, Optional[float]]:
    """
    Extract canonical flat features from a stored JSONL record.

    Returns a dict mapping feature names to values.  If a value is
    missing or malformed, it is set to None — never silently imputed.
    """
    features: Dict[str, Optional[float]] = {}

    for feature_name, path in _FEATURE_MAP.items():
        try:
            obj = record
            for key in path:
                obj = obj[key]
            features[feature_name] = float(obj)
        except (KeyError, TypeError, ValueError, IndexError):
            features[feature_name] = None

    return features


def parse_record_timestamp(record: dict) -> Optional[datetime]:
    """Parse the timestamp from a stored JSONL record."""
    ts_raw = record.get("timestamp")
    if ts_raw is None:
        return None
    try:
        if isinstance(ts_raw, str):
            ts = datetime.fromisoformat(ts_raw)
        else:
            return None
    except (ValueError, TypeError):
        return None

    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


class _NodeState:
    """Per-node state container."""

    def __init__(
        self,
        window_hours: int,
        threshold_medium: float,
        threshold_high: float,
        bootstrap_samples: int,
        min_samples_monitoring: int,
        min_samples_regression: int,
    ):
        self.window = RollingWindow(window_hours=window_hours)
        self.detector = AnomalyDetector(
            threshold_medium=threshold_medium,
            threshold_high=threshold_high,
            bootstrap_samples=bootstrap_samples,
            min_samples_monitoring=min_samples_monitoring,
            min_samples_regression=min_samples_regression,
        )
        self.last_refit_time: float = 0.0
        self.lock = threading.Lock()


class AnomalyEngine:
    """
    Top-level anomaly engine.

    Parameters are read from the NavosEdge configuration at startup.
    """

    def __init__(
        self,
        window_hours: int = 24,
        model_update_interval_minutes: int = 15,
        threshold_medium: float = 2.0,
        threshold_high: float = 3.0,
        bootstrap_samples: int = 5,
        min_samples_monitoring: int = 10,
        min_samples_regression: int = 30,
        stale_data_minutes: int = 30,
    ):
        self.window_hours = window_hours
        self.model_update_interval_s = model_update_interval_minutes * 60.0
        self.threshold_medium = threshold_medium
        self.threshold_high = threshold_high
        self.bootstrap_samples = bootstrap_samples
        self.min_samples_monitoring = min_samples_monitoring
        self.min_samples_regression = min_samples_regression
        self.stale_data_minutes = stale_data_minutes

        self._nodes: Dict[str, _NodeState] = {}
        self._nodes_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(
        self,
        node_id: str,
        record: dict,
    ) -> dict:
        """
        Analyse a single observation for anomalies.

        Parameters
        ----------
        node_id : str
        record : dict
            The full stored JSONL record (with timestamp, environment,
            particulate_matter, gas_sensors keys).

        Returns
        -------
        dict
            Structured anomaly report.
        """
        state = self._get_or_create_node(node_id)

        with state.lock:
            # Parse timestamp
            ts = parse_record_timestamp(record)
            if ts is None:
                return self._error_result("Cannot parse timestamp from record")

            # Extract features
            features = extract_features_from_record(record)

            # Build observation
            obs = Observation(timestamp=ts, features=features)

            # Add to rolling window
            state.window.add(obs)

            # Check staleness
            newest = state.window.newest()
            if newest is not None:
                age_min = (datetime.now(timezone.utc) - newest.timestamp).total_seconds() / 60.0
                if age_min > self.stale_data_minutes:
                    result = DetectionResult()
                    result.timestamp = ts
                    result.data_status = "STALE"
                    result.system_state = SystemState.DEGRADED
                    result.explanations = [
                        f"Data is stale ({age_min:.0f} min since newest reading)"
                    ]
                    return result.to_dict()

            # Periodically refit baselines
            now_mono = time.monotonic()
            if (now_mono - state.last_refit_time) >= self.model_update_interval_s:
                self._refit_baselines(state)
                state.last_refit_time = now_mono

            # Run detection
            detection = state.detector.detect(obs, state.window)
            return detection.to_dict()

    def load_history(
        self,
        node_id: str,
        records: List[dict],
    ) -> int:
        """
        Bulk-load historical records into the rolling window for a node.

        Returns the number of valid observations loaded.
        """
        state = self._get_or_create_node(node_id)

        with state.lock:
            observations: List[Observation] = []
            for rec in records:
                ts = parse_record_timestamp(rec)
                if ts is None:
                    continue
                features = extract_features_from_record(rec)
                observations.append(Observation(timestamp=ts, features=features))

            # Sort chronologically
            observations.sort(key=lambda o: o.timestamp)

            state.window.load_bulk(observations)

            # Fit baselines from loaded history
            self._refit_baselines(state)
            state.last_refit_time = time.monotonic()

            return state.window.count()

    def get_system_state(self, node_id: str) -> str:
        """Return the current system state for a node."""
        state = self._get_or_create_node(node_id)
        with state.lock:
            return state.detector._determine_state(state.window).value

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_or_create_node(self, node_id: str) -> _NodeState:
        with self._nodes_lock:
            if node_id not in self._nodes:
                self._nodes[node_id] = _NodeState(
                    window_hours=self.window_hours,
                    threshold_medium=self.threshold_medium,
                    threshold_high=self.threshold_high,
                    bootstrap_samples=self.bootstrap_samples,
                    min_samples_monitoring=self.min_samples_monitoring,
                    min_samples_regression=self.min_samples_regression,
                )
            return self._nodes[node_id]

    def _refit_baselines(self, state: _NodeState) -> None:
        """Refit regression baselines from the current window data."""
        window = state.window
        detector = state.detector

        for feature_name in ALL_FEATURES:
            ts_vals = window.get_time_series(feature_name)
            if not ts_vals:
                continue

            timestamps = [tv[0] for tv in ts_vals]
            values = [tv[1] for tv in ts_vals]

            # Fit baseline
            detector.baseline.fit(feature_name, timestamps, values)

            # Rebuild residual history from fitted baseline
            if detector.baseline.has_regression(feature_name):
                predicted = []
                for ts in timestamps:
                    p = detector.baseline.predict(feature_name, ts)
                    if p is not None:
                        predicted.append(p)
                    else:
                        predicted.append(values[timestamps.index(ts)])
                detector.residuals.load_from_history(
                    feature_name, predicted, values
                )

    @staticmethod
    def _error_result(message: str) -> dict:
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "anomaly": {"detected": False, "score": 0.0, "severity": "NONE"},
            "sensor_evidence": {},
            "data_quality": {
                "status": "ERROR",
                "missing_features": [],
                "features_used": [],
                "sensor_health": "UNKNOWN",
                "confidence": "INSUFFICIENT_DATA",
            },
            "system_state": "DEGRADED",
            "anomaly_source": "UNKNOWN",
            "anomaly_source_detail": "",
            "explanations": [message],
        }
