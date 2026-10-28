"""
Detailed diagnostic breakdown of AnomalyEngine behavior across the 35-day historical dataset.
Analyses performance across all scenarios, fault types, and detector components.
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


def diagnose():
    print("=" * 80)
    print("PHASE 1 & 2: ANOMALY ENGINE BASELINE DIAGNOSIS & REPRODUCTION")
    print("=" * 80)

    gen_config = GenerationConfig(
        node_id="diag-node-faults",
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

    for i, rec in enumerate(records):
        prov = rec.get("provenance", {})
        fault = prov.get("fault")
        scenario = prov.get("scenario")
        ts = rec["timestamp"]

        res = engine.analyse("diag-node-faults", rec)
        anom = res.get("anomaly", {})
        detected = anom.get("detected", False)
        severity = anom.get("severity", "NONE")
        score = anom.get("score", 0.0)
        source = res.get("anomaly_source", "UNKNOWN")
        detail = res.get("anomaly_source_detail", "")
        dq = res.get("data_quality", {})
        
        # Check sensor issues in feature results
        feat_issues = []
        for fn, fr in res.get("sensor_evidence", {}).items():
            if fr.get("sensor_health") != "GOOD":
                feat_issues.append(f"{fn}:{fr.get('sensor_health')}")

        rows.append({
            "idx": i,
            "timestamp": ts,
            "scenario": scenario,
            "fault": fault,
            "is_hw_fault": (fault is not None and fault != "warmup"),
            "detected": detected,
            "severity": severity,
            "score": score,
            "anomaly_source": source,
            "anomaly_source_detail": detail,
            "sensor_issues": feat_issues,
            "status": dq.get("status"),
        })

    df = pd.DataFrame(rows)
    print(f"\nTotal evaluated records: {len(df)}")
    print(f"Scenario distribution:\n{df['scenario'].value_counts()}")
    print(f"\nFault distribution:\n{df['fault'].value_counts(dropna=False)}")

    # 1. Baseline metric reproduction (using naive detected or severity >= MEDIUM)
    df["naive_flag"] = df["detected"] | df["severity"].isin(["MEDIUM", "HIGH", "CRITICAL"])
    
    tp_naive = len(df[df["is_hw_fault"] & df["naive_flag"]])
    fp_naive = len(df[~df["is_hw_fault"] & df["naive_flag"]])
    tn_naive = len(df[~df["is_hw_fault"] & ~df["naive_flag"]])
    fn_naive = len(df[df["is_hw_fault"] & ~df["naive_flag"]])

    prec_naive = tp_naive / (tp_naive + fp_naive) if (tp_naive + fp_naive) > 0 else 0
    rec_naive = tp_naive / (tp_naive + fn_naive) if (tp_naive + fn_naive) > 0 else 0
    fpr_naive = fp_naive / (fp_naive + tn_naive) if (fp_naive + tn_naive) > 0 else 0

    print("\n--- NAIVE DETECTION BASELINE (Treating ANY detected anomaly as HW fault) ---")
    print(f"  TP: {tp_naive}, FP: {fp_naive}, TN: {tn_naive}, FN: {fn_naive}")
    print(f"  Precision: {prec_naive*100:.2f}% | Recall: {rec_naive*100:.2f}% | FPR: {fpr_naive*100:.2f}%")

    # 2. What caused the 951 False Positives?
    print("\n--- BREAKDOWN OF NAIVE FALSE POSITIVES BY SCENARIO ---")
    fp_df = df[~df["is_hw_fault"] & df["naive_flag"]]
    print(fp_df["scenario"].value_counts())
    print("\nAnomaly Source attributed to these False Positives:")
    print(fp_df["anomaly_source"].value_counts())

    # 3. Breakdown of Hardware Faults Detection by Fault Type
    print("\n--- BREAKDOWN OF ACTUAL HARDWARE FAULTS DETECTION ---")
    hw_df = df[df["is_hw_fault"]]
    for ftype, grp in hw_df.groupby("fault"):
        detected_cnt = len(grp[grp["naive_flag"]])
        total_cnt = len(grp)
        src_counts = grp["anomaly_source"].value_counts().to_dict()
        print(f"  Fault: {ftype:<15s} -> Detected: {detected_cnt}/{total_cnt} ({detected_cnt/total_cnt*100:.1f}%) | Sources: {src_counts}")

    # 4. What if we use anomaly_source == "SENSOR_FAULT"?
    df["hw_classified_flag"] = (df["anomaly_source"] == "SENSOR_FAULT") | (df["sensor_issues"].apply(len) > 0)
    tp_cls = len(df[df["is_hw_fault"] & df["hw_classified_flag"]])
    fp_cls = len(df[~df["is_hw_fault"] & df["hw_classified_flag"]])
    tn_cls = len(df[~df["is_hw_fault"] & ~df["hw_classified_flag"]])
    fn_cls = len(df[df["is_hw_fault"] & ~df["hw_classified_flag"]])

    prec_cls = tp_cls / (tp_cls + fp_cls) if (tp_cls + fp_cls) > 0 else 0
    rec_cls = tp_cls / (tp_cls + fn_cls) if (tp_cls + fn_cls) > 0 else 0
    fpr_cls = fp_cls / (fp_cls + tn_cls) if (fp_cls + tn_cls) > 0 else 0

    print("\n--- SOURCE-ATTRIBUTED HARDWARE FAULT DETECTION ---")
    print(f"  TP: {tp_cls}, FP: {fp_cls}, TN: {tn_cls}, FN: {fn_cls}")
    print(f"  Precision: {prec_cls*100:.2f}% | Recall: {rec_cls*100:.2f}% | FPR: {fpr_cls*100:.2f}%")


if __name__ == "__main__":
    diagnose()
