"""
Evaluate Targeted Fix V2 on Delhi Challenge (seed=888).
Tests refined classify_anomaly_source and clean baseline protection.
"""

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np
import pandas as pd

root_dir = Path(__file__).resolve().parents[1]
server_dir = root_dir / "Intelligence" / "Server"

if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

from app.anomaly.detector import ALL_FEATURES
from app.anomaly.engine import AnomalyEngine, _NodeState
from app.anomaly.sensor_health import (
    PHYSICAL_DEVICES,
    SensorHealthChecker,
    SensorStatus,
    SourceClassification,
    _RAILED_THRESHOLDS,
    _VALID_RANGES,
)
from Simulator.historical_generator import GenerationConfig, HistoricalDatasetGenerator


class TargetedSensorHealthCheckerV2(SensorHealthChecker):
    def __init__(self):
        super().__init__()
        # Track consecutive elevation count per physical device
        self._elevation_counts: Dict[str, int] = {}

    def classify_anomaly_source(
        self,
        feature_statuses: Dict[str, SensorStatus],
        feature_scores: Dict[str, float],
        threshold: float = 2.0,
        feature_values: Optional[Dict[str, Optional[float]]] = None,
        recent_values_map: Optional[Dict[str, List[float]]] = None,
    ) -> SourceClassification:
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
        # Calculate max score and voltage residual per gas device
        gas_dev_scores: Dict[str, float] = {}
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
            
            # Uncorroborated gas fault:
            # Other gas sensors are not elevated (< threshold)
            if max_other < threshold:
                # If PM is not elevated, score >= 3.0 is a clear single-channel fault
                if pm_max_score < threshold and gscore >= 3.0:
                    hw_fault_devs.add(gdev)
                # If PM is elevated (Delhi winter or traffic), require sustained elevation
                # (>= 3 consecutive steps) or strong deviation (gscore >= 4.0) to prevent
                # traffic onset false alarms while reliably catching sustained drift
                elif pm_max_score >= threshold:
                    v_res = abs(feature_values.get(f"{gdev}_voltage_V", 0.0) - 0.82) if feature_values else 0.0
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


class TargetedNodeStateV2(_NodeState):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.detector.health_checker = TargetedSensorHealthCheckerV2()
        self.faulty_readings: Set[Tuple[str, datetime]] = set()


class TargetedAnomalyEngineV2(AnomalyEngine):
    def _get_or_create_node(self, node_id: str) -> TargetedNodeStateV2:
        with self._nodes_lock:
            if node_id not in self._nodes:
                self._nodes[node_id] = TargetedNodeStateV2(
                    window_hours=self.window_hours,
                    threshold_medium=self.threshold_medium,
                    threshold_high=self.threshold_high,
                    bootstrap_samples=self.bootstrap_samples,
                    min_samples_monitoring=self.min_samples_monitoring,
                    min_samples_regression=self.min_samples_regression,
                )
            return self._nodes[node_id]

    def _refit_baselines(self, state: TargetedNodeStateV2) -> None:
        """Refit regression baselines from current window data, filtering corrupted/railed values and known faulty readings."""
        window = state.window
        detector = state.detector

        for feature_name in ALL_FEATURES:
            ts_vals = window.get_time_series(feature_name)
            if not ts_vals:
                continue

            railed = _RAILED_THRESHOLDS.get(feature_name)
            vrange = _VALID_RANGES.get(feature_name)

            filtered_ts = []
            filtered_vals = []
            for ts, val in ts_vals:
                if railed is not None and (val <= railed[0] or val >= railed[1]):
                    continue
                if vrange is not None and (val < vrange[0] or val > vrange[1]):
                    continue
                if (feature_name, ts) in state.faulty_readings:
                    continue
                filtered_ts.append(ts)
                filtered_vals.append(val)

            # If too many points were flagged as faulty, ensure at least 10 clean points or skip refit
            if len(filtered_vals) < 10:
                continue

            # Fit baseline with clean observations
            detector.baseline.fit(feature_name, filtered_ts, filtered_vals)

            # Rebuild residual history from fitted baseline
            if detector.baseline.has_regression(feature_name):
                predicted = []
                for ts, v in zip(filtered_ts, filtered_vals):
                    p = detector.baseline.predict(feature_name, ts)
                    if p is not None:
                        predicted.append(v - p)
                if predicted:
                    detector.residuals._residuals[feature_name] = predicted[-detector.residuals.max_residual_history:]

    def analyse(self, node_id: str, record: dict) -> dict:
        result = super().analyse(node_id, record)
        state = self._get_or_create_node(node_id)
        if result.get("is_hardware_fault"):
            ts_str = result.get("timestamp")
            if ts_str:
                ts = datetime.fromisoformat(ts_str)
                ev = result.get("sensor_evidence", {})
                for fname, fr in ev.items():
                    sc = fr.get("score", 0.0)
                    hlth = fr.get("sensor_health", "GOOD")
                    # If this specific channel is degraded/failed or elevated due to hardware fault
                    if hlth in ("FAILED", "DEGRADED") or sc >= self.threshold_medium:
                        state.faulty_readings.add((fname, ts))
        # Keep faulty_readings bounded to window
        if state.window.oldest():
            oldest_ts = state.window.oldest().timestamp
            state.faulty_readings = {(f, t) for (f, t) in state.faulty_readings if t >= oldest_ts}
        return result


def evaluate_candidate_v2():
    print("=" * 80)
    print("RUNNING CANDIDATE EVALUATION V2 ON DELHI CHALLENGE (seed=888)")
    print("=" * 80)

    gen_config = GenerationConfig(
        node_id="eval-delhi-888",
        days=35,
        sampling_interval_seconds=300.0,
        seed=888,
        start_date="2024-11-01",
        location="delhi",
        inject_faults=True,
    )
    records = HistoricalDatasetGenerator(gen_config).generate_all()

    engine = TargetedAnomalyEngineV2()

    rows = []
    fault_episodes = {}
    cur_fault = None
    start_ts = None

    for i, rec in enumerate(records):
        prov = rec.get("provenance", {})
        fault = prov.get("fault")
        scen = prov.get("scenario")
        ts = rec["timestamp"]
        is_hw = (fault is not None and fault != "warmup")

        if is_hw:
            if cur_fault != fault:
                cur_fault = fault
                start_ts = ts
                fault_episodes[cur_fault] = {
                    "start": start_ts,
                    "first_detected": None,
                    "delay_min": None,
                }
        else:
            cur_fault = None

        res = engine.analyse("eval-delhi-888", rec)
        source = res.get("anomaly_source", "UNKNOWN")
        is_hw_alert = res.get("is_hardware_fault", False) or (source in ("SENSOR_FAULT", "MIXED"))
        is_env_alert = res.get("is_environmental_event", False) or (source in ("ENVIRONMENTAL", "MIXED"))

        if is_hw and is_hw_alert and cur_fault is not None:
            if fault_episodes[cur_fault]["first_detected"] is None:
                fault_episodes[cur_fault]["first_detected"] = ts
                t0 = datetime.fromisoformat(fault_episodes[cur_fault]["start"])
                t1 = datetime.fromisoformat(ts)
                fault_episodes[cur_fault]["delay_min"] = (t1 - t0).total_seconds() / 60.0

        rows.append({
            "idx": i,
            "timestamp": ts,
            "scenario": scen,
            "fault": fault,
            "is_hw_fault": is_hw,
            "is_hw_alert": is_hw_alert,
            "is_env_alert": is_env_alert,
        })

    df = pd.DataFrame(rows)

    tp = int(len(df[df["is_hw_fault"] & df["is_hw_alert"]]))
    fp = int(len(df[~df["is_hw_fault"] & df["is_hw_alert"]]))
    tn = int(len(df[~df["is_hw_fault"] & ~df["is_hw_alert"]]))
    fn = int(len(df[df["is_hw_fault"] & ~df["is_hw_alert"]]))

    prec = float(tp / (tp + fp) if (tp + fp) > 0 else 0.0)
    rec = float(tp / (tp + fn) if (tp + fn) > 0 else 0.0)
    fpr = float(fp / (fp + tn) if (fp + tn) > 0 else 0.0)
    f1 = float(2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0)

    print(f"Total evaluated: {len(df)}")
    print(f"TP: {tp} / 348 | FP: {fp} | TN: {tn} | FN: {fn}")
    print(f"Precision: {prec*100:.2f}% (Baseline was: 94.20%)")
    print(f"Recall:    {rec*100:.2f}% (Baseline was: 56.03%)")
    print(f"FPR:       {fpr*100:.2f}% (Baseline was: 0.12%)")
    print(f"F1 Score:  {f1*100:.2f}% (Baseline was: 70.27%)")

    print("\nPer-Fault Recall:")
    hw_df = df[df["is_hw_fault"]]
    for ftype, grp in hw_df.groupby("fault"):
        detected_cnt = int(len(grp[grp["is_hw_alert"]]))
        total_cnt = int(len(grp))
        dmin = fault_episodes.get(ftype, {}).get("delay_min")
        print(f"  {ftype:<15s}: {detected_cnt}/{total_cnt} ({detected_cnt/total_cnt*100:.1f}%) | Delay: {dmin} min")

    print("\nPer-Scenario False Alerts:")
    for scen, grp in df.groupby("scenario"):
        hw_fp = int(len(grp[~grp["is_hw_fault"] & grp["is_hw_alert"]]))
        tot_non_hw = int(len(grp[~grp["is_hw_fault"]]))
        env_cnt = int(len(grp[grp["is_env_alert"]]))
        print(f"  {scen:<25s}: HW FP = {hw_fp}/{tot_non_hw} ({hw_fp/tot_non_hw*100:.2f}%) | Env Events = {env_cnt}")


if __name__ == "__main__":
    evaluate_candidate_v2()
