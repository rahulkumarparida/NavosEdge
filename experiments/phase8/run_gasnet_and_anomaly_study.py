"""
NavosEdge Phase 8 (Parts B & C) — GasNet Validation & Anomaly Detection FPR Investigation.

Preserves all thresholds and artifacts; produces reproducible diagnostic evidence.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
import random
import statistics
import sys
import time
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_recall_fscore_support

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_ROOT = REPO_ROOT / "Intelligence" / "Server"
for p in (str(SERVER_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from Simulator.generator import ScenarioGenerator
from app.anomaly.engine import AnomalyEngine
from app.services.numpy_inference import NumpyGasNetAdapter
from app.services.safety_gate import MQ_VOLTAGE_MAX, MQ_VOLTAGE_MIN

SEED = 42
OUT_DIR = Path(__file__).resolve().parent / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def run_gasnet_validation() -> Dict[str, Any]:
    logging.getLogger("app.services.numpy_inference").setLevel(logging.CRITICAL)
    artifacts_dir = SERVER_ROOT / "artifacts"
    weights_sha = hashlib.sha256((artifacts_dir / "gasnet_weights.npz").read_bytes()).hexdigest()
    meta = json.loads((artifacts_dir / "model_metadata.json").read_text(encoding="utf-8"))

    adapter = NumpyGasNetAdapter(artifacts_dir=artifacts_dir, n_mc=20, deterministic_seed=SEED)
    adapter.load()

    # 1. Leakage / duplicate check across seeds 42, 101, 777
    seed_rows: Dict[int, List[Dict[str, Any]]] = {}
    seed_sigs: Dict[int, set] = {}
    for s in (42, 101, 777):
        p = REPO_ROOT / "test_data" / "phase2_model_audit" / f"synthetic_tinygasnet_eval_seed_{s}.json"
        data = json.loads(p.read_text(encoding="utf-8"))["data"]
        seed_rows[s] = data
        seed_sigs[s] = {(r["expected_gas"], r["mq2"], r["mq9"], r["mq135"], r["t"], r["h"]) for r in data}

    overlap_42_101 = len(seed_sigs[42] & seed_sigs[101])
    overlap_42_777 = len(seed_sigs[42] & seed_sigs[777])
    overlap_101_777 = len(seed_sigs[101] & seed_sigs[777])

    all_rows = seed_rows[42] + seed_rows[101] + seed_rows[777]
    y_true, y_pred, uncs = [], [], []
    for r in all_rows:
        res = asyncio.run(adapter.predict(r["mq2"], r["mq9"], r["mq135"], r["t"], r["h"]))
        y_true.append(r["expected_gas"])
        y_pred.append(res.gas_class or "UNKNOWN")
        uncs.append(float(res.uncertainty or 0.0))

    labels_5 = sorted(meta["class_labels"])
    acc = accuracy_score(y_true, y_pred)
    f1_5 = f1_score(y_true, y_pred, labels=labels_5, average="macro", zero_division=0)

    # 2. Noise Perturbation Stability (5% and 15% relative Gaussian noise on seed=777)
    rng = random.Random(SEED)
    noise_results = {}
    for noise_pct in (0.05, 0.15):
        yt_n, yp_n, unc_n = [], [], []
        for r in seed_rows[777]:
            mq2 = max(0.11, min(4.89, r["mq2"] * (1.0 + rng.gauss(0.0, noise_pct))))
            mq9 = max(0.11, min(4.89, r["mq9"] * (1.0 + rng.gauss(0.0, noise_pct))))
            mq135 = max(0.11, min(4.89, r["mq135"] * (1.0 + rng.gauss(0.0, noise_pct))))
            res = asyncio.run(adapter.predict(mq2, mq9, mq135, r["t"], r["h"]))
            yt_n.append(r["expected_gas"])
            yp_n.append(res.gas_class or "UNKNOWN")
            unc_n.append(float(res.uncertainty or 0.0))
        noise_results[f"gaussian_{int(noise_pct*100)}pct"] = {
            "accuracy": round(float(accuracy_score(yt_n, yp_n)), 4),
            "macro_f1_5class": round(float(f1_score(yt_n, yp_n, labels=labels_5, average="macro", zero_division=0)), 4),
            "mean_uncertainty": round(statistics.mean(unc_n), 4),
        }

    # 3. Legacy Training/mq_synthetic_dataset.csv incompatibility diagnosis
    df_leg = pd.read_csv(REPO_ROOT / "Training" / "mq_synthetic_dataset.csv")
    low_rail_mask = (df_leg["MQ2_V"] < MQ_VOLTAGE_MIN) | (df_leg["MQ9_V"] < MQ_VOLTAGE_MIN) | (df_leg["MQ135_V"] < MQ_VOLTAGE_MIN)
    high_rail_mask = (df_leg["MQ2_V"] > MQ_VOLTAGE_MAX) | (df_leg["MQ9_V"] > MQ_VOLTAGE_MAX) | (df_leg["MQ135_V"] > MQ_VOLTAGE_MAX)

    return {
        "weights_sha256": weights_sha,
        "reproduced_baseline": {
            "n_samples": len(all_rows),
            "accuracy": round(float(acc), 4),
            "macro_f1_5class": round(float(f1_5), 4),
            "mean_uncertainty": round(statistics.mean(uncs), 4),
            "duplicate_overlaps": {
                "42_vs_101": overlap_42_101,
                "42_vs_777": overlap_42_777,
                "101_vs_777": overlap_101_777,
            },
        },
        "perturbation_stability_seed777": noise_results,
        "legacy_csv_diagnosis": {
            "file": "Training/mq_synthetic_dataset.csv",
            "n_rows": int(len(df_leg)),
            "legacy_classes": sorted(df_leg["gas_label"].unique().tolist()),
            "model_classes": labels_5,
            "rows_below_safety_gate_0_100V": int(low_rail_mask.sum()),
            "pct_below_safety_gate": round(float(low_rail_mask.mean() * 100.0), 2),
            "rows_above_safety_gate_4_900V": int(high_rail_mask.sum()),
            "clean_air_mean_voltages": {
                "MQ2_V": round(float(df_leg[df_leg["gas_label"] == "CleanAir"]["MQ2_V"].mean()), 3),
                "MQ9_V": round(float(df_leg[df_leg["gas_label"] == "CleanAir"]["MQ9_V"].mean()), 3),
                "MQ135_V": round(float(df_leg[df_leg["gas_label"] == "CleanAir"]["MQ135_V"].mean()), 3),
            },
            "co_mean_voltages": {
                "MQ2_V": round(float(df_leg[df_leg["gas_label"] == "CO"]["MQ2_V"].mean()), 3),
                "MQ9_V": round(float(df_leg[df_leg["gas_label"] == "CO"]["MQ9_V"].mean()), 3),
                "MQ135_V": round(float(df_leg[df_leg["gas_label"] == "CO"]["MQ135_V"].mean()), 3),
            },
            "conclusion": "Incompatible legacy schema: 8 classes vs 5 classes, inverted voltage polarity (CleanAir > CO), and majority of rows < 0.100V trigger SensorSafetyGate.",
        },
    }


def run_anomaly_validation() -> Dict[str, Any]:
    # 1. Reproduce Phase 7 85-step controlled sequence and trace the exact 7 FPs
    engine_syn = AnomalyEngine(min_samples_monitoring=10, min_samples_regression=20)
    clean_gen = ScenarioGenerator(node_id="anom-p8", scenario="clean_background", seed=SEED)
    pm_gen = ScenarioGenerator(node_id="anom-p8", scenario="pm_spike", seed=SEED + 1)
    gas_gen = ScenarioGenerator(node_id="anom-p8", scenario="gas_spike", seed=SEED + 2)

    fp_details = []
    fn_details = []
    y_true, y_pred = [], []
    for step in range(85):
        if step < 40:
            payload = clean_gen.next_payload(60.0)
            gt = 0
        elif step < 55:
            payload = pm_gen.next_payload(60.0)
            gt = 1
        elif step < 70:
            payload = clean_gen.next_payload(60.0)
            gt = 0
        else:
            payload = gas_gen.next_payload(60.0)
            gt = 1

        rep = engine_syn.analyse("anom-p8", payload)
        anom = rep.get("anomaly") or {}
        is_anom = 1 if anom.get("detected") else 0
        if step >= 10:
            y_true.append(gt)
            y_pred.append(is_anom)
            if gt == 0 and is_anom == 1:
                ev = rep.get("sensor_evidence") or {}
                top_feats = sorted(
                    ((k, v.get("score", 0.0), v.get("actual"), v.get("expected")) for k, v in ev.items()),
                    key=lambda x: x[1],
                    reverse=True,
                )[:3]
                fp_details.append(
                    {
                        "step": step,
                        "score": anom.get("score"),
                        "severity": anom.get("severity"),
                        "is_hardware_fault": anom.get("is_hardware_fault"),
                        "top_features": [
                            {"feature": f, "score": s, "actual": a, "expected": e} for f, s, a, e in top_feats
                        ],
                    }
                )
            elif gt == 1 and is_anom == 0:
                fn_details.append({"step": step, "score": anom.get("score"), "pm2_5": payload["particulate_matter"]["PM2_5"]})

    # 2. Long 6-hour normal diurnal run (360 samples @ 60s) -> False alarms per hour
    engine_diurnal = AnomalyEngine(min_samples_monitoring=10, min_samples_regression=30)
    gen_6h = ScenarioGenerator(node_id="anom-6h", scenario="clean_background", seed=SEED)
    diurnal_fps = 0
    for step in range(360):
        rep = engine_diurnal.analyse("anom-6h", gen_6h.next_payload(60.0))
        if step >= 10 and (rep.get("anomaly") or {}).get("detected"):
            diurnal_fps += 1

    # 3. Inspect exact 2 flagged anomalies & 2 sensor faults in REAL_RECORDED_DATA session_1
    df_mpm = pd.read_csv(REPO_ROOT / "dataset" / "MPM_10_Dataset" / "session_1.csv")
    df_dht = pd.read_csv(REPO_ROOT / "dataset" / "DHT22_Dataset" / "session_01.csv")
    df_mq = pd.read_csv(REPO_ROOT / "dataset" / "MQ_Dataset" / "session_01.csv")
    n_real = min(300, len(df_mpm), len(df_dht), len(df_mq))
    engine_real = AnomalyEngine(min_samples_monitoring=10, min_samples_regression=20)
    real_events = []
    for i in range(n_real):
        rec = {
            "node_id": "real-session-01",
            "timestamp": str(df_mpm.iloc[i]["timestamp"]),
            "environment": {
                "temperature_C": float(df_dht.iloc[i]["temperature_c"]),
                "humidity_pct": float(df_dht.iloc[i]["humidity_percent"]),
            },
            "particulate_matter": {
                "PM1_0": float(df_mpm.iloc[i]["pm1_0"]),
                "PM2_5": float(df_mpm.iloc[i]["pm2_5"]),
                "PM10": float(df_mpm.iloc[i]["pm10"]),
            },
            "gas_sensors": {
                "MQ2": {"raw_adc": int(df_mq.iloc[i]["mq2_raw_adc"]), "voltage_V": float(df_mq.iloc[i]["mq2_ao_voltage"])},
                "MQ9": {"raw_adc": int(df_mq.iloc[i]["mq9_raw_adc"]), "voltage_V": float(df_mq.iloc[i]["mq9_ao_voltage"])},
                "MQ135": {"raw_adc": int(df_mq.iloc[i]["mq135_raw_adc"]), "voltage_V": float(df_mq.iloc[i]["mq135_ao_voltage"])},
            },
        }
        rep = engine_real.analyse("real-session-01", rec)
        anom = rep.get("anomaly") or {}
        if anom.get("detected") or anom.get("is_hardware_fault"):
            real_events.append(
                {
                    "row_index": i,
                    "timestamp": rec["timestamp"],
                    "pm1_0": rec["particulate_matter"]["PM1_0"],
                    "pm2_5": rec["particulate_matter"]["PM2_5"],
                    "pm10": rec["particulate_matter"]["PM10"],
                    "detected": anom.get("detected"),
                    "is_hardware_fault": anom.get("is_hardware_fault"),
                    "score": anom.get("score"),
                    "severity": anom.get("severity"),
                }
            )

    return {
        "controlled_85step_diagnosis": {
            "n_eval": len(y_true),
            "fp_count": len(fp_details),
            "fn_count": len(fn_details),
            "fp_details": fp_details,
            "fn_details": fn_details,
        },
        "diurnal_6hour_normal_run": {
            "n_samples": 360,
            "post_warmup_samples": 350,
            "simulated_hours": 350 / 60.0,
            "false_positives": diurnal_fps,
            "false_positives_per_hour": round(diurnal_fps / (350 / 60.0), 3),
        },
        "real_session1_flagged_events": real_events,
    }


def main() -> None:
    out = {
        "gasnet_validation": run_gasnet_validation(),
        "anomaly_validation": run_anomaly_validation(),
    }
    out_file = OUT_DIR / "phase8_gasnet_and_anomaly.json"
    out_file.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("Saved GasNet & Anomaly study to", out_file)
    print("GasNet legacy rows < 0.100V:", out["gasnet_validation"]["legacy_csv_diagnosis"]["rows_below_safety_gate_0_100V"], "/", out["gasnet_validation"]["legacy_csv_diagnosis"]["n_rows"])
    print("GasNet 5% noise acc:", out["gasnet_validation"]["perturbation_stability_seed777"]["gaussian_5pct"]["accuracy"])
    print("GasNet 15% noise acc:", out["gasnet_validation"]["perturbation_stability_seed777"]["gaussian_15pct"]["accuracy"])
    print("Anomaly 6h normal FPs:", out["anomaly_validation"]["diurnal_6hour_normal_run"]["false_positives"], "per hour:", out["anomaly_validation"]["diurnal_6hour_normal_run"]["false_positives_per_hour"])
    print("Anomaly 85-step FP steps:", [d["step"] for d in out["anomaly_validation"]["controlled_85step_diagnosis"]["fp_details"]])
    print("Real session_1 flagged events:", out["anomaly_validation"]["real_session1_flagged_events"])


if __name__ == "__main__":
    main()

