"""
Refined Anomaly Engine Evaluation with Physical Sensor Device Fusion.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set

import numpy as np
import pandas as pd

root_dir = Path(__file__).resolve().parents[1]
server_dir = root_dir / "Intelligence" / "Server"

if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

from app.anomaly.detector import (
    ALL_FEATURES,
    AnomalyDetector,
    Confidence,
    DetectionResult,
    FeatureResult,
    Severity,
    SystemState,
)
from app.anomaly.engine import AnomalyEngine, _NodeState
from app.anomaly.sensor_health import (
    _MAX_JUMP,
    _RAILED_THRESHOLDS,
    _VALID_RANGES,
    SensorHealthChecker,
    SensorStatus,
)
from app.anomaly.window import Observation, RollingWindow
from Simulator.historical_generator import GenerationConfig, HistoricalDatasetGenerator

# Mapping from feature name to physical sensor device
PHYSICAL_DEVICES = {
    "MQ2_voltage_V": "MQ2", "MQ2_raw_adc": "MQ2",
    "MQ9_voltage_V": "MQ9", "MQ9_raw_adc": "MQ9",
    "MQ135_voltage_V": "MQ135", "MQ135_raw_adc": "MQ135",
    "PM1_0": "PMS", "PM2_5": "PMS", "PM10": "PMS",
    "temperature_C": "TEMP", "humidity_pct": "HUM",
}


class RefinedSensorHealthChecker(SensorHealthChecker):
    def check_feature(
        self,
        feature_name: str,
        value: Optional[float],
        recent_values: Optional[List[float]] = None,
        previous_value: Optional[float] = None,
    ) -> Tuple[SensorStatus, List[str]]:
        issues: List[str] = []

        if value is None:
            return SensorStatus.MISSING, [f"{feature_name}: value is missing"]

        # 1. Valid range
        vrange = _VALID_RANGES.get(feature_name)
        if vrange is not None:
            lo, hi = vrange
            if value < lo or value > hi:
                issues.append(f"{feature_name}: value {value} outside [{lo}, {hi}]")
                return SensorStatus.FAILED, issues

        # 2. Railed to supply rail
        railed = _RAILED_THRESHOLDS.get(feature_name)
        if railed is not None:
            lo, hi = railed
            if value <= lo:
                issues.append(f"{feature_name}: railed to GND (value={value} <= {lo})")
                return SensorStatus.FAILED, issues
            elif value >= hi:
                issues.append(f"{feature_name}: railed to VCC (value={value} >= {hi})")
                return SensorStatus.FAILED, issues

        # 3. Sudden impossible jump relative to actual previous reading
        if previous_value is not None and feature_name in _MAX_JUMP:
            jump = abs(value - previous_value)
            if jump > _MAX_JUMP[feature_name]:
                issues.append(f"{feature_name}: sudden jump of {jump:.2f} (max {_MAX_JUMP[feature_name]})")
                return SensorStatus.DEGRADED, issues

        # 4. Analog freeze (exact identical values on continuous ADC/voltage channels)
        if feature_name.endswith("_raw_adc") or feature_name.endswith("_voltage_V"):
            if recent_values is not None and len(recent_values) >= 6:
                last_n = recent_values[-6:]
                if len(set(last_n)) == 1:
                    issues.append(f"{feature_name}: analog channel frozen across 6 readings")
                    return SensorStatus.DEGRADED, issues

        return SensorStatus.GOOD, issues

    def classify_anomaly_source(
        self,
        feature_statuses: Dict[str, SensorStatus],
        feature_scores: Dict[str, float],
        feature_values: Dict[str, Optional[float]],
        recent_values_map: Dict[str, List[float]],
        threshold: float = 2.0,
    ) -> Tuple[str, str, bool, bool]:
        """
        Distinguishes hardware faults from environmental anomalies by physical device.
        Returns: (source_label, explanation, is_hw_fault, is_env_event)
        """
        hw_fault_devs: Set[str] = set()

        # 1. Hard failures (railed GND/VCC, invalid range, missing)
        for f, status in feature_statuses.items():
            dev = PHYSICAL_DEVICES.get(f, f)
            if status in (SensorStatus.FAILED, SensorStatus.MISSING):
                hw_fault_devs.add(dev)

        # 2. Frozen continuous analog channels (raw_adc/voltage constant across >= 6 readings with elevated score)
        for f, status in feature_statuses.items():
            if status == SensorStatus.DEGRADED and (f.endswith("_raw_adc") or f.endswith("_voltage_V")):
                if feature_scores.get(f, 0.0) >= 1.8:
                    dev = PHYSICAL_DEVICES.get(f, f)
                    hw_fault_devs.add(dev)

        # Check preliminary environmental elevation across physical devices
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
        if not has_env_corroboration:
            for f, score in feature_scores.items():
                if score >= 2.0 and f.startswith("MQ"):
                    dev = PHYSICAL_DEVICES.get(f, f)
                    r_vals = recent_values_map.get(f, [])
                    if len(r_vals) >= 8:
                        last_8 = r_vals[-8:]
                        span = max(last_8) - min(last_8)
                        var = float(np.var(last_8))
                        if span < 0.04 and var < 1.5e-4:
                            hw_fault_devs.add(dev)

        # 4. Uncorroborated single-channel gas drift
        gas_dev_scores = {}
        for f, sc in feature_scores.items():
            dev = PHYSICAL_DEVICES.get(f, f)
            if dev in ("MQ2", "MQ9", "MQ135"):
                gas_dev_scores[dev] = max(gas_dev_scores.get(dev, 0.0), sc)

        for gdev, gscore in gas_dev_scores.items():
            other_gas = [sc for d, sc in gas_dev_scores.items() if d != gdev]
            max_other = max(other_gas) if other_gas else 0.0
            if gscore >= 3.0 and max_other < 1.5 and pm_max_score < 1.5:
                hw_fault_devs.add(gdev)

        # Identify healthy physical devices with elevated readings
        elevated_healthy_devs = set()
        for f, sc in feature_scores.items():
            dev = PHYSICAL_DEVICES.get(f, f)
            if dev not in hw_fault_devs and sc >= threshold:
                elevated_healthy_devs.add(dev)

        has_hw = len(hw_fault_devs) > 0
        has_env = len(elevated_healthy_devs) >= 2 or (len(elevated_healthy_devs) == 1 and "PMS" in elevated_healthy_devs and pm_max_score >= 3.0)

        if has_hw and has_env:
            source = "MIXED"
            expl = f"Hardware fault on {', '.join(sorted(hw_fault_devs))} with concurrent environmental elevation on {', '.join(sorted(elevated_healthy_devs))}"
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

        return source, expl, has_hw, has_env


class RefinedDetectionResult(DetectionResult):
    __slots__ = ("is_hardware_fault", "is_environmental_event")

    def __init__(self):
        super().__init__()
        self.is_hardware_fault: bool = False
        self.is_environmental_event: bool = False


class RefinedAnomalyDetector(AnomalyDetector):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.health_checker = RefinedSensorHealthChecker()

    def detect(self, observation: Observation, window: RollingWindow) -> DetectionResult:
        result = RefinedDetectionResult()
        result.timestamp = observation.timestamp
        self.observation_count = window.count()
        result.system_state = self._determine_state(window)

        feature_scores: Dict[str, float] = {}
        feature_statuses: Dict[str, SensorStatus] = {}
        recent_values_map: Dict[str, List[float]] = {}
        available_features: List[str] = []
        missing_features: List[str] = []

        for feature_name in ALL_FEATURES:
            actual = observation.features.get(feature_name)
            recent_vals = window.get_values(feature_name)
            recent_values_map[feature_name] = recent_vals
            
            # Proper previous value (recent_vals[-1] is actual because window.add was already called)
            prev_val = recent_vals[-2] if len(recent_vals) >= 2 else None

            sensor_status, sensor_issues = self.health_checker.check_feature(
                feature_name, actual, recent_vals, prev_val
            )
            feature_statuses[feature_name] = sensor_status

            if actual is None or sensor_status == SensorStatus.MISSING:
                missing_features.append(feature_name)
                result.feature_results[feature_name] = FeatureResult(
                    feature_name=feature_name, actual=None, expected=None, residual=None,
                    score=0.0, status_label="UNAVAILABLE", sensor_status=SensorStatus.MISSING,
                    sensor_issues=sensor_issues,
                )
                continue

            if sensor_status == SensorStatus.FAILED:
                missing_features.append(feature_name)
                exp = self.baseline.predict(feature_name, observation.timestamp)
                res_val = (actual - exp) if exp is not None else 0.0
                score_val = 5.0
                feature_scores[feature_name] = score_val
                result.feature_results[feature_name] = FeatureResult(
                    feature_name=feature_name, actual=actual, expected=exp, residual=res_val,
                    score=score_val, status_label="SENSOR_FAILED", sensor_status=sensor_status,
                    sensor_issues=sensor_issues,
                )
                continue

            available_features.append(feature_name)
            ts_list = [ts for ts, _ in window.get_time_series(feature_name)]
            val_list = window.get_values(feature_name)

            expected = self.baseline.predict(
                feature_name, observation.timestamp,
                recent_values=val_list[-10:] if val_list else None,
                recent_timestamps=ts_list[-10:] if ts_list else None,
            )

            if expected is None:
                result.feature_results[feature_name] = FeatureResult(
                    feature_name=feature_name, actual=actual, expected=None, residual=None,
                    score=0.0, status_label="NO_BASELINE", sensor_status=sensor_status,
                    sensor_issues=sensor_issues,
                )
                continue

            residual = actual - expected
            min_floor = self.baseline.get_min_deviation_floor(feature_name)
            self.residuals.record_residual(feature_name, residual)
            score = self.residuals.compute_score(feature_name, residual, min_floor)
            feature_scores[feature_name] = score

            if score >= self.threshold_high:
                status_label = "ANOMALOUS"
            elif score >= self.threshold_medium:
                status_label = "ELEVATED"
            else:
                status_label = "NORMAL"

            result.feature_results[feature_name] = FeatureResult(
                feature_name=feature_name, actual=actual, expected=round(expected, 4),
                residual=round(residual, 4), score=round(score, 3), status_label=status_label,
                sensor_status=sensor_status, sensor_issues=sensor_issues,
            )

        result.missing_features = missing_features
        result.features_used = available_features
        result.data_status = "OK" if not missing_features else ("PARTIAL_DATA" if available_features else "INSUFFICIENT_DATA")

        if result.system_state == SystemState.BOOTSTRAPPING:
            result.detected = False
            result.combined_score = 0.0
            result.severity = Severity.NONE
            result.confidence = Confidence.INSUFFICIENT_DATA
            result.explanations = ["System is bootstrapping — collecting baseline data"]
            return result

        result.combined_score = self._fuse_scores(feature_scores) if feature_scores else 0.0

        if result.combined_score >= self.threshold_high:
            result.severity = Severity.HIGH
            result.detected = True
        elif result.combined_score >= self.threshold_medium:
            result.severity = Severity.MEDIUM
            result.detected = True
        else:
            result.severity = Severity.LOW
            result.detected = False

        # Classify anomaly source using physical device fusion
        source, detail, is_hw, is_env = self.health_checker.classify_anomaly_source(
            feature_statuses, feature_scores, observation.features, recent_values_map, self.threshold_medium
        )
        result.anomaly_source = source
        result.anomaly_source_detail = detail

        # Add explicit boolean fields to result for downstream clarity
        setattr(result, "is_hardware_fault", is_hw)
        setattr(result, "is_environmental_event", is_env)

        if is_hw:
            result.detected = True
            result.severity = Severity.HIGH

        result.confidence = self._estimate_confidence(window, available_features, missing_features, result.system_state)
        result.explanations = self._build_explanations(result, feature_scores)
        return result


class RefinedAnomalyEngine(AnomalyEngine):
    def _get_or_create_node(self, node_id: str) -> _NodeState:
        with self._nodes_lock:
            if node_id not in self._nodes:
                state = _NodeState(
                    window_hours=self.window_hours,
                    threshold_medium=self.threshold_medium,
                    threshold_high=self.threshold_high,
                    bootstrap_samples=self.bootstrap_samples,
                    min_samples_monitoring=self.min_samples_monitoring,
                    min_samples_regression=self.min_samples_regression,
                )
                state.detector = RefinedAnomalyDetector(
                    threshold_medium=self.threshold_medium,
                    threshold_high=self.threshold_high,
                    bootstrap_samples=self.bootstrap_samples,
                    min_samples_monitoring=self.min_samples_monitoring,
                    min_samples_regression=self.min_samples_regression,
                )
                self._nodes[node_id] = state
            return self._nodes[node_id]

    def _refit_baselines(self, state: _NodeState) -> None:
        """Prevent baseline contamination by excluding railed readings."""
        window = state.window
        detector = state.detector

        for feature_name in ALL_FEATURES:
            ts_vals = window.get_time_series(feature_name)
            if not ts_vals:
                continue

            railed = _RAILED_THRESHOLDS.get(feature_name)
            filtered_ts, filtered_vals = [], []
            for ts, val in ts_vals:
                if railed is not None and (val <= railed[0] or val >= railed[1]):
                    continue
                filtered_ts.append(ts)
                filtered_vals.append(val)

            if len(filtered_vals) < 5:
                continue

            detector.baseline.fit(feature_name, filtered_ts, filtered_vals)

            if detector.baseline.has_regression(feature_name):
                predicted = []
                for ts in filtered_ts:
                    p = detector.baseline.predict(feature_name, ts)
                    if p is not None:
                        predicted.append(p)
                    else:
                        predicted.append(filtered_vals[filtered_ts.index(ts)])
                detector.residuals.load_from_history(
                    feature_name, predicted, filtered_vals
                )


def evaluate_refined():
    gen_config = GenerationConfig(
        node_id="eval-refined",
        days=35,
        sampling_interval_seconds=300.0,
        seed=42,
        start_date="2024-09-01",
        location="bhubaneswar",
        inject_faults=True,
    )
    generator = HistoricalDatasetGenerator(gen_config)
    records = generator.generate_all()

    engine = RefinedAnomalyEngine()
    
    rows = []
    delays = []
    cur_fault_start = None

    print(f"Generated {len(records)} records. Beginning analysis...", flush=True)

    for i, rec in enumerate(records):
        if i % 1000 == 0:
            print(f"Processed {i}/{len(records)} records...", flush=True)
        prov = rec.get("provenance", {})
        fault = prov.get("fault")
        scen = prov.get("scenario")
        ts = rec["timestamp"]
        is_hw = (fault is not None and fault != "warmup")

        if is_hw and cur_fault_start is None:
            cur_fault_start = ts
        elif not is_hw:
            cur_fault_start = None

        res = engine.analyse("eval-refined", rec)
        source = res.get("anomaly_source", "UNKNOWN")
        is_hw_alert = (source in ("SENSOR_FAULT", "MIXED"))
        is_env_alert = (source in ("ENVIRONMENTAL", "MIXED"))

        if is_hw and is_hw_alert and cur_fault_start is not None:
            t0 = datetime.fromisoformat(cur_fault_start)
            t1 = datetime.fromisoformat(ts)
            delays.append((t1 - t0).total_seconds() / 60.0)

        rows.append({
            "fault": fault,
            "scenario": scen,
            "is_hw_fault": is_hw,
            "is_hw_alert": is_hw_alert,
            "is_env_alert": is_env_alert,
            "source": source,
        })

    df = pd.DataFrame(rows)

    tp = len(df[df["is_hw_fault"] & df["is_hw_alert"]])
    fp = len(df[~df["is_hw_fault"] & df["is_hw_alert"]])
    tn = len(df[~df["is_hw_fault"] & ~df["is_hw_alert"]])
    fn = len(df[df["is_hw_fault"] & ~df["is_hw_alert"]])

    prec = tp / (tp + fp) if (tp + fp) > 0 else 0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
    mean_delay = np.mean(delays) if delays else 0

    print("================================================================================")
    print("REFINED HARDWARE FAULT DETECTION RESULTS")
    print("================================================================================")
    print(f"  TP: {tp} / 348")
    print(f"  FP: {fp}  (Baseline was 951)")
    print(f"  TN: {tn}")
    print(f"  FN: {fn}  (Baseline was 133)")
    print(f"  Precision:       {prec*100:.2f}% (Baseline was: 18.44%)")
    print(f"  Recall:          {rec*100:.2f}% (Baseline was: 61.78%)")
    print(f"  False Pos. Rate: {fpr*100:.2f}% (Baseline was: 9.80%)")
    print(f"  F1 Score:        {f1*100:.2f}% (Baseline was: 28.40%)")
    print(f"  Mean Delay:      {mean_delay:.1f} minutes")

    print("\n--- PER-FAULT RECALL ---")
    hw_df = df[df["is_hw_fault"]]
    for ftype, grp in hw_df.groupby("fault"):
        cnt = len(grp[grp["is_hw_alert"]])
        tot = len(grp)
        print(f"  {ftype:<15s}: {cnt}/{tot} ({cnt/tot*100:.1f}%)")

    print("\n--- PER-SCENARIO FALSE POSITIVE ALERTS ---")
    for scen, grp in df.groupby("scenario"):
        hw_fp = len(grp[~grp["is_hw_fault"] & grp["is_hw_alert"]])
        tot_non_hw = len(grp[~grp["is_hw_fault"]])
        env_cnt = len(grp[grp["is_env_alert"]])
        print(f"  {scen:<25s}: HW FP = {hw_fp}/{tot_non_hw} ({hw_fp/tot_non_hw*100:.2f}%) | Env Events = {env_cnt}")


if __name__ == "__main__":
    evaluate_refined()
