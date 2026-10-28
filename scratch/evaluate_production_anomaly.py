"""
Evaluate production AnomalyEngine across the 35-day historical dataset (10,056 readings).
Verifies precision, recall, false positive rate, detection delays, and per-scenario breakdowns.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import numpy as np
import pandas as pd
import sys

root_dir = Path(__file__).resolve().parents[1]
server_dir = root_dir / "Intelligence" / "Server"

if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

from app.anomaly.engine import AnomalyEngine
from Simulator.historical_generator import GenerationConfig, HistoricalDatasetGenerator


def evaluate():
    print("=" * 80)
    print("EVALUATING PRODUCTION ANOMALY ENGINE ACROSS 35-DAY HISTORICAL DATASET")
    print("=" * 80)

    gen_config = GenerationConfig(
        node_id="eval-prod",
        days=35,
        sampling_interval_seconds=300.0,
        seed=42,
        start_date="2024-09-01",
        location="bhubaneswar",
        inject_faults=True,
    )
    generator = HistoricalDatasetGenerator(gen_config)
    records = generator.generate_all()

    engine = AnomalyEngine()
    
    rows = []
    fault_episodes = {}
    cur_fault = None
    start_ts = None

    print(f"Generated {len(records)} records. Replaying through AnomalyEngine...", flush=True)

    for i, rec in enumerate(records):
        if i % 2000 == 0:
            print(f"Processed {i}/{len(records)} records...", flush=True)
            
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
                    "delay_min": None
                }
        else:
            cur_fault = None

        res = engine.analyse("eval-prod", rec)
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

        rows.append({
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
            "source": source,
            "detail": detail,
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

    print("\n" + "=" * 80)
    print("PRODUCTION ANOMALY ENGINE EVALUATION RESULTS")
    print("=" * 80)
    print(f"  True Positives (TP) : {tp} / 348")
    print(f"  False Positives (FP): {fp}  (Baseline was: 951)")
    print(f"  True Negatives (TN) : {tn}  (Baseline was: 8757)")
    print(f"  False Negatives (FN): {fn}  (Baseline was: 133)")
    print(f"  Hardware Precision  : {prec*100:.2f}% (Baseline was: 18.44%)")
    print(f"  Hardware Recall     : {rec*100:.2f}% (Baseline was: 61.78%)")
    print(f"  False Positive Rate : {fpr*100:.2f}% (Baseline was: 9.80%)")
    print(f"  Hardware F1 Score   : {f1*100:.2f}% (Baseline was: 28.40%)")

    print("\n--- PER-FAULT RECALL ---")
    hw_df = df[df["is_hw_fault"]]
    for ftype, grp in hw_df.groupby("fault"):
        cnt = len(grp[grp["is_hw_alert"]])
        tot = len(grp)
        print(f"  {ftype:<15s}: {cnt}/{tot} ({cnt/tot*100:.1f}%)")

    print("\n--- DETECTION DELAYS PER FAULT EPISODE ---")
    for ftype, ep in fault_episodes.items():
        dmin = ep['delay_min']
        d_str = f"{dmin:.1f} min" if dmin is not None else "NOT DETECTED"
        print(f"  {ftype:<15s}: first_detected={ep['first_detected']} | delay={d_str}")

    print("\n--- PER-SCENARIO BREAKDOWN ---")
    for scen, grp in df.groupby("scenario"):
        hw_fp = len(grp[~grp["is_hw_fault"] & grp["is_hw_alert"]])
        tot_non_hw = len(grp[~grp["is_hw_fault"]])
        env_cnt = len(grp[grp["is_env_alert"]])
        print(f"  {scen:<25s}: HW FP = {hw_fp}/{tot_non_hw} ({hw_fp/tot_non_hw*100:.2f}%) | Env Events = {env_cnt}/{len(grp)}")

    # Save results to json for reporting
    results_summary = {
        "metrics": {
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "false_positive_rate": round(fpr, 4),
            "f1_score": round(f1, 4),
        },
        "per_fault": {
            ftype: {
                "detected": int(len(grp[grp["is_hw_alert"]])),
                "total": int(len(grp)),
                "recall": round(len(grp[grp["is_hw_alert"]]) / len(grp), 4),
                "delay_minutes": fault_episodes.get(ftype, {}).get("delay_min"),
            }
            for ftype, grp in hw_df.groupby("fault")
        },
        "per_scenario": {
            scen: {
                "hw_fp": int(len(grp[~grp["is_hw_fault"] & grp["is_hw_alert"]])),
                "total_non_hw": int(len(grp[~grp["is_hw_fault"]])),
                "env_events": int(len(grp[grp["is_env_alert"]])),
                "total_readings": int(len(grp)),
            }
            for scen, grp in df.groupby("scenario")
        }
    }
    
    out_path = root_dir / "test_data" / "production_anomaly_evaluation.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results_summary, f, indent=2)
    print(f"\nSaved production evaluation summary to {out_path}")


if __name__ == "__main__":
    evaluate()
