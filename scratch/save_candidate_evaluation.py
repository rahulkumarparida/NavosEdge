"""
Save Candidate evaluation results to test_data/anomaly_candidate_delhi/
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import numpy as np
import pandas as pd

root_dir = Path(__file__).resolve().parents[1]
server_dir = root_dir / "Intelligence" / "Server"

if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

from app.anomaly.engine import AnomalyEngine
from Simulator.historical_generator import GenerationConfig, HistoricalDatasetGenerator


def get_git_info() -> Dict[str, str]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(root_dir), text=True
        ).strip()
    except Exception:
        commit = "unknown"
    try:
        branch = subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=str(root_dir), text=True
        ).strip()
    except Exception:
        branch = "unknown"
    return {"commit": commit, "branch": branch}


def run_candidate_evaluation(output_dir: Path) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    git_info = get_git_info()
    timestamp = datetime.now(timezone.utc).isoformat()

    gen_config = GenerationConfig(
        node_id="eval-delhi-888",
        days=35,
        sampling_interval_seconds=300.0,
        seed=888,
        start_date="2024-11-01",  # Winter season
        location="delhi",
        inject_faults=True,
    )
    generator = HistoricalDatasetGenerator(gen_config)
    delhi_records = generator.generate_all()

    engine = AnomalyEngine()

    rows = []
    fault_episodes = {}
    cur_fault = None
    start_ts = None

    failed_cases = {
        "false_negatives": [],
        "false_positives": [],
    }

    for i, rec in enumerate(delhi_records):
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
        detail = res.get("anomaly_source_detail", "")
        is_hw_alert = res.get("is_hardware_fault", False) or (source in ("SENSOR_FAULT", "MIXED"))
        is_env_alert = res.get("is_environmental_event", False) or (source in ("ENVIRONMENTAL", "MIXED"))
        anom = res.get("anomaly", {})
        detected = anom.get("detected", False)
        severity = anom.get("severity", "NONE")
        score = anom.get("score", 0.0)

        if is_hw and is_hw_alert and cur_fault is not None:
            if fault_episodes[cur_fault]["first_detected"] is None:
                fault_episodes[cur_fault]["first_detected"] = ts
                t0 = datetime.fromisoformat(fault_episodes[cur_fault]["start"])
                t1 = datetime.fromisoformat(ts)
                fault_episodes[cur_fault]["delay_min"] = (t1 - t0).total_seconds() / 60.0

        case_info = {
            "idx": i,
            "timestamp": ts,
            "scenario": scen,
            "fault": fault,
            "is_hw_fault": is_hw,
            "is_hw_alert": is_hw_alert,
            "is_env_alert": is_env_alert,
            "detected": detected,
            "severity": severity,
            "score": score,
            "anomaly_source": source,
            "anomaly_source_detail": detail,
            "gas_sensors": rec.get("gas_sensors"),
            "particulate_matter": rec.get("particulate_matter"),
            "environment": rec.get("environment"),
            "sensor_evidence": res.get("sensor_evidence"),
        }

        if is_hw and not is_hw_alert:
            failed_cases["false_negatives"].append(case_info)
        elif not is_hw and is_hw_alert:
            failed_cases["false_positives"].append(case_info)

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

    per_fault = {}
    hw_df = df[df["is_hw_fault"]]
    for ftype, grp in hw_df.groupby("fault"):
        detected_cnt = int(len(grp[grp["is_hw_alert"]]))
        total_cnt = int(len(grp))
        per_fault[str(ftype)] = {
            "detected": detected_cnt,
            "total": total_cnt,
            "recall": round(detected_cnt / total_cnt, 4),
            "delay_min": fault_episodes.get(ftype, {}).get("delay_min"),
        }

    per_scenario = {}
    for scen, grp in df.groupby("scenario"):
        hw_fp = int(len(grp[~grp["is_hw_fault"] & grp["is_hw_alert"]]))
        tot_non_hw = int(len(grp[~grp["is_hw_fault"]]))
        env_cnt = int(len(grp[grp["is_env_alert"]]))
        per_scenario[str(scen)] = {
            "hw_fp": hw_fp,
            "total_non_hw": tot_non_hw,
            "hw_fp_rate": round(hw_fp / tot_non_hw, 4) if tot_non_hw > 0 else 0.0,
            "env_events": env_cnt,
            "total_readings": int(len(grp)),
        }

    results = {
        "dataset_identity": "Delhi Winter-Smog Synthetic Challenge (35 days, 5-min interval)",
        "location": "delhi",
        "start_date": "2024-11-01",
        "random_seed": 888,
        "sampling_interval_seconds": 300.0,
        "days": 35,
        "total_records": len(df),
        "code_commit": git_info["commit"],
        "git_branch": git_info["branch"],
        "timestamp": timestamp,
        "metrics": {
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "false_positive_rate": round(fpr, 4),
            "f1_score": round(f1, 4),
        },
        "per_fault": per_fault,
        "detection_delays_minutes": {
            k: v["delay_min"] for k, v in per_fault.items()
        },
        "mean_detection_delay_minutes": float(np.mean([
            v["delay_min"] for v in per_fault.values() if v["delay_min"] is not None
        ])),
        "per_scenario": per_scenario,
    }

    with open(output_dir / "candidate_metrics.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    with open(output_dir / "candidate_failed_cases.json", "w", encoding="utf-8") as f:
        json.dump(failed_cases, f, indent=2)

    print(f"Saved candidate evaluation results to {output_dir / 'candidate_metrics.json'}")
    print(f"Saved {len(failed_cases['false_negatives'])} false negatives and {len(failed_cases['false_positives'])} false positives to {output_dir / 'candidate_failed_cases.json'}")
    return results


if __name__ == "__main__":
    out = root_dir / "test_data" / "anomaly_candidate_delhi"
    res = run_candidate_evaluation(out)
