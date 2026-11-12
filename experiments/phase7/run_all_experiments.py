"""
NavosEdge Phase 7 — Reproducible Experimental Evaluation & Performance Benchmark Suite.

Runs completely isolated from production `data/` and `local_dataset/` using temporary
directories and deterministic random seeds (SEED = 42).
Never fabricates measurements; every output is tagged with its evidence provenance:
  - REAL_RECORDED_DATA
  - EXTERNAL_REFERENCE
  - SYNTHETIC
  - MOCKED
"""

from __future__ import annotations

import asyncio
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
import glob
import json
import math
import os
from pathlib import Path
import random
import statistics
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import httpx
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_ROOT = REPO_ROOT / "Intelligence" / "Server"
MANAGER_ROOT = REPO_ROOT / "Manager"

for p in (str(SERVER_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from Simulator.generator import ScenarioGenerator
from app.anomaly.engine import AnomalyEngine
from app.core.config import get_settings
from app.emergency.database import EmergencyDatabase
from app.emergency.notification_provider import SimulatedNotificationProvider
from app.emergency.notification_service import EmergencyNotificationService
from app.emergency.schemas import (
    ConsentStatus,
    EmergencyContactCreate,
    EmergencyEventStatus,
    NodeRegistration,
    NotificationChannel,
    ResidentCreate,
)
from app.forecast.model import generate_forecast
from app.main import create_app
from app.schemas.sensor import SensorPayload
from app.services.numpy_inference import NumpyGasNetAdapter
from app.source_classifier.classifier import SourceClassifier

SEED = 42
OUT_DIR = Path(__file__).resolve().parent / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def get_process_rss_mb() -> Optional[float]:
    """Read current process WorkingSetSize (RSS) on Windows without psutil."""
    if os.name != "nt":
        return None

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = PROCESS_MEMORY_COUNTERS()
    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    if ctypes.windll.psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        return round(counters.WorkingSetSize / (1024 * 1024), 2)
    return None


def summarize_latencies(samples_ms: List[float]) -> Dict[str, Any]:
    if not samples_ms:
        return {"n": 0}
    s = sorted(samples_ms)
    n = len(s)
    p95_idx = min(n - 1, int(math.ceil(0.95 * n)) - 1)
    return {
        "n": n,
        "min_ms": round(s[0], 3),
        "median_ms": round(statistics.median(s), 3),
        "mean_ms": round(statistics.mean(s), 3),
        "p95_ms": round(s[p95_idx], 3),
        "max_ms": round(s[-1], 3),
    }


# ---------------------------------------------------------------------------
# 1. Dataset Inventory & Provenance
# ---------------------------------------------------------------------------


def profile_datasets() -> Dict[str, Any]:
    inventory: Dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "real_recorded_data": {},
        "external_reference": {},
        "synthetic": {},
        "mixed_test_logs": {},
    }

    for folder, ts_col in (
        ("DHT22_Dataset", "timestamp"),
        ("MPM_10_Dataset", "timestamp"),
        ("MQ_Dataset", "timestamp"),
    ):
        files = sorted(glob.glob(str(REPO_ROOT / "dataset" / folder / "*.csv")))
        dfs = [pd.read_csv(f) for f in files]
        df = pd.concat(dfs, ignore_index=True)
        ts = pd.to_datetime(df[ts_col], errors="coerce")
        dt_sec = ts.diff().dt.total_seconds().dropna()
        pos_dt = dt_sec[(dt_sec > 0) & (dt_sec < 60)]
        stats = {}
        for col in df.select_dtypes(include=[np.number]).columns:
            stats[col] = {
                "min": round(float(df[col].min()), 3),
                "median": round(float(df[col].median()), 3),
                "max": round(float(df[col].max()), 3),
                "mean": round(float(df[col].mean()), 3),
                "std": round(float(df[col].std()), 3),
            }
        inventory["real_recorded_data"][folder] = {
            "provenance": "REAL_RECORDED_DATA",
            "files": len(files),
            "rows": int(len(df)),
            "columns": list(df.columns),
            "time_range": [str(ts.min()), str(ts.max())],
            "median_sampling_interval_s": round(float(pos_dt.median()), 2) if len(pos_dt) else None,
            "missing_values": {k: int(v) for k, v in df.isna().sum().items()},
            "labeled": False,
            "numeric_summary": stats,
        }

    # External reference: Open-Meteo Bhubaneswar & Dhenkanal
    for fname in (
        "airquality_bhubaneswar_2024-11-01_2024-12-05.json",
        "airquality_dhenkanal_2024-09-01_2024-10-06.json",
    ):
        fpath = REPO_ROOT / "data" / "historical_cache" / fname
        if fpath.exists():
            with open(fpath, "r", encoding="utf-8") as fh:
                raw = json.load(fh)
            hourly = raw.get("hourly", {})
            times = hourly.get("time", [])
            pm25 = [x for x in hourly.get("pm2_5", []) if x is not None]
            pm10 = [x for x in hourly.get("pm10", []) if x is not None]
            inventory["external_reference"][fname] = {
                "provenance": "EXTERNAL_REFERENCE",
                "rows": len(times),
                "time_range": [times[0], times[-1]] if times else [],
                "sampling_interval_s": 3600,
                "features": list(hourly.keys()),
                "pm2_5_summary": {
                    "min": round(min(pm25), 2),
                    "median": round(statistics.median(pm25), 2),
                    "max": round(max(pm25), 2),
                    "mean": round(statistics.mean(pm25), 2),
                } if pm25 else {},
                "pm10_summary": {
                    "min": round(min(pm10), 2),
                    "median": round(statistics.median(pm10), 2),
                    "max": round(max(pm10), 2),
                    "mean": round(statistics.mean(pm10), 2),
                } if pm10 else {},
                "labeled": False,
            }

    # Synthetic labeled GasNet dataset
    mq_path = REPO_ROOT / "Training" / "mq_synthetic_dataset.csv"
    df_mq = pd.read_csv(mq_path)
    inventory["synthetic"]["Training/mq_synthetic_dataset.csv"] = {
        "provenance": "SYNTHETIC",
        "rows": int(len(df_mq)),
        "columns": list(df_mq.columns),
        "label_counts": {str(k): int(v) for k, v in df_mq["gas_label"].value_counts().items()},
        "missing_values": {k: int(v) for k, v in df_mq.isna().sum().items()},
        "labeled": True,
    }

    # Mixed test logs (local_dataset)
    local_files = sorted(glob.glob(str(REPO_ROOT / "local_dataset" / "*.csv")))
    if local_files:
        df_loc = pd.concat([pd.read_csv(f) for f in local_files], ignore_index=True)
        inventory["mixed_test_logs"]["local_dataset"] = {
            "provenance": "MIXED_TEST_AND_SIMULATOR_LOGS",
            "files": len(local_files),
            "rows": int(len(df_loc)),
            "distinct_node_ids": int(df_loc["node_id"].nunique()),
            "note": "Contains automated pytest/simulator node_ids (e.g., test-node-01, gate-test-01); NOT treated as pure physical hardware field data.",
        }

    return inventory


# ---------------------------------------------------------------------------
# 2. Model Evaluations (GasNet, SourceClassifier, AnomalyEngine, Forecasting)
# ---------------------------------------------------------------------------


def evaluate_gasnet() -> Dict[str, Any]:
    import logging
    logging.getLogger("app.services.numpy_inference").setLevel(logging.CRITICAL)
    artifacts_dir = SERVER_ROOT / "artifacts"
    adapter = NumpyGasNetAdapter(artifacts_dir=artifacts_dir, n_mc=20, deterministic_seed=SEED)
    adapter.load()

    eval_files = [
        REPO_ROOT / "test_data" / "phase2_model_audit" / "synthetic_tinygasnet_eval_seed_42.json",
        REPO_ROOT / "test_data" / "phase2_model_audit" / "synthetic_tinygasnet_eval_seed_101.json",
        REPO_ROOT / "test_data" / "phase2_model_audit" / "synthetic_tinygasnet_eval_seed_777.json",
    ]
    rows: List[Dict[str, Any]] = []
    for ef in eval_files:
        with open(ef, "r", encoding="utf-8") as fh:
            rows.extend(json.load(fh).get("data", []))

    y_true: List[str] = []
    y_pred: List[str] = []
    uncertainties: List[float] = []
    confidences: List[float] = []
    infer_times_ms: List[float] = []

    for row in rows:
        t0 = time.perf_counter()
        res = asyncio.run(
            adapter.predict(
                mq2_v=float(row["mq2"]),
                mq9_v=float(row["mq9"]),
                mq135_v=float(row["mq135"]),
                temperature_c=float(row["t"]),
                humidity_pct=float(row["h"]),
            )
        )
        infer_times_ms.append((time.perf_counter() - t0) * 1000.0)
        y_true.append(str(row["expected_gas"]))
        y_pred.append(str(res.gas_class or "Unknown"))
        uncertainties.append(float(res.uncertainty or 0.0))
        confidences.append(float(res.class_confidence or 0.0))

    labels = sorted(list(set(y_true) | set(y_pred)))
    acc = accuracy_score(y_true, y_pred)
    macro_f1 = f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
    p, r, f1, sup = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=labels).tolist()

    per_class = {
        lbl: {
            "precision": round(float(p[i]), 4),
            "recall": round(float(r[i]), 4),
            "f1": round(float(f1[i]), 4),
            "support": int(sup[i]),
        }
        for i, lbl in enumerate(labels)
    }

    # Uncertainty under OOD / extreme perturbation (100 synthetic perturbed samples)
    rng = random.Random(SEED)
    ood_uncertainties: List[float] = []
    for _ in range(100):
        res_ood = asyncio.run(
            adapter.predict(
                mq2_v=rng.uniform(3.8, 4.9),
                mq9_v=rng.uniform(0.05, 0.25),
                mq135_v=rng.uniform(3.9, 4.9),
                temperature_c=55.0,
                humidity_pct=95.0,
            )
        )
        ood_uncertainties.append(float(res_ood.uncertainty or 0.0))

    return {
        "provenance": "SYNTHETIC",
        "dataset": "test_data/phase2_model_audit/synthetic_tinygasnet_eval_seed_{42,101,777}.json",
        "n_samples": len(rows),
        "accuracy": round(float(acc), 4),
        "macro_f1": round(float(macro_f1), 4),
        "labels": labels,
        "confusion_matrix": cm,
        "per_class": per_class,
        "uncertainty_in_dist_mean": round(statistics.mean(uncertainties), 4),
        "uncertainty_in_dist_p95": round(sorted(uncertainties)[int(0.95 * len(uncertainties))], 4),
        "uncertainty_ood_mean": round(statistics.mean(ood_uncertainties), 4),
        "confidence_in_dist_mean": round(statistics.mean(confidences), 4),
        "inference_latency": summarize_latencies(infer_times_ms),
        "limitation": "Evaluated on synthetic labeled data; not physical calibrated gas chamber measurements.",
    }


def evaluate_source_classifier() -> Dict[str, Any]:
    clf = SourceClassifier(artifacts_dir=SERVER_ROOT / "artifacts")
    clf.load()

    scenario_to_expected = {
        "clean_background": "CLEAN_OR_BACKGROUND",
        "traffic": "TRAFFIC",
        "heavy_dust": "HEAVY_DUST",
        "construction": "CONSTRUCTION_ACTIVITY",
        "biomass_burning": "BIOMASS_OR_WASTE_BURNING",
        "combustion_smoke": "COOKING_OR_FUEL_COMBUSTION",
        "industrial": "INDUSTRIAL_OR_GENERATOR_EMISSIONS",
        "indoor_activity": "INDOOR_ACTIVITY",
    }

    y_true: List[str] = []
    y_pred: List[str] = []
    uncertain_count = 0
    abstain_count = 0

    for scen, expected_label in scenario_to_expected.items():
        gen = ScenarioGenerator(node_id=f"eval-{scen}", scenario=scen, seed=SEED)
        for _ in range(30):
            payload = SensorPayload(**gen.next_payload(interval_seconds=10.0))
            res = clf.classify(payload)
            y_true.append(expected_label)
            pred = res.get("top_source") or "ABSTAIN"
            y_pred.append(pred)
            unc_obj = res.get("uncertainty") or {}
            if isinstance(unc_obj, dict) and unc_obj.get("flag"):
                uncertain_count += 1
            elif isinstance(unc_obj, bool) and unc_obj:
                uncertain_count += 1
            if pred in ("UNKNOWN", "ABSTAIN", None):
                abstain_count += 1

    labels = sorted(list(scenario_to_expected.values()))
    all_labels = sorted(list(set(y_true) | set(y_pred)))
    acc = accuracy_score(y_true, y_pred)
    macro_f1 = f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0)
    p, r, f1, sup = precision_recall_fscore_support(y_true, y_pred, labels=labels, zero_division=0)
    cm = confusion_matrix(y_true, y_pred, labels=all_labels).tolist()

    return {
        "provenance": "SYNTHETIC",
        "generator": "Simulator.generator.ScenarioGenerator (seed=42, 30 samples/scenario)",
        "n_samples": len(y_true),
        "accuracy": round(float(acc), 4),
        "macro_f1": round(float(macro_f1), 4),
        "uncertainty_flagged_rate": round(uncertain_count / len(y_true), 4),
        "abstention_rate": round(abstain_count / len(y_true), 4),
        "eval_labels": labels,
        "matrix_labels": all_labels,
        "confusion_matrix": cm,
        "per_class": {
            lbl: {
                "precision": round(float(p[i]), 4),
                "recall": round(float(r[i]), 4),
                "f1": round(float(f1[i]), 4),
                "support": int(sup[i]),
            }
            for i, lbl in enumerate(labels)
        },
    }


def evaluate_anomaly_engine() -> Dict[str, Any]:
    # A. Synthetic controlled benchmark: 40 clean baseline + 15 sudden PM spikes + 15 clean + 15 gas spikes
    engine_syn = AnomalyEngine(min_samples_monitoring=10, min_samples_regression=20)
    y_true: List[int] = []
    y_pred: List[int] = []
    pm_detect_delay: Optional[int] = None
    gas_detect_delay: Optional[int] = None

    clean_gen = ScenarioGenerator(node_id="anom-syn", scenario="clean_background", seed=SEED)
    pm_gen = ScenarioGenerator(node_id="anom-syn", scenario="pm_spike", seed=SEED + 1)
    gas_gen = ScenarioGenerator(node_id="anom-syn", scenario="gas_spike", seed=SEED + 2)

    timeline_records: List[Dict[str, Any]] = []
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

        report = engine_syn.analyse("anom-syn", payload)
        # Skip warmup (< 10 samples) for FPR/precision metrics
        anom = report.get("anomaly") or {}
        is_anom = 1 if anom.get("detected") else 0
        if step >= 10:
            y_true.append(gt)
            y_pred.append(is_anom)
        if 40 <= step < 55 and is_anom == 1 and pm_detect_delay is None:
            pm_detect_delay = step - 40
        if step >= 70 and is_anom == 1 and gas_detect_delay is None:
            gas_detect_delay = step - 70
        timeline_records.append(
            {
                "step": step,
                "gt_anomaly": gt,
                "pred_anomaly": is_anom,
                "score": round(float(anom.get("score") or 0.0), 3),
                "state": anom.get("severity", ""),
                "pm2_5": round(payload["particulate_matter"]["PM2_5"], 2),
            }
        )

    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    fnr = fn / (fn + tp) if (fn + tp) else 0.0

    # B. Real recorded data replay: MPM_10 session_1 + DHT22 session_01 + MQ session_01 (first 300 rows)
    df_mpm = pd.read_csv(REPO_ROOT / "dataset" / "MPM_10_Dataset" / "session_1.csv")
    df_dht = pd.read_csv(REPO_ROOT / "dataset" / "DHT22_Dataset" / "session_01.csv")
    df_mq = pd.read_csv(REPO_ROOT / "dataset" / "MQ_Dataset" / "session_01.csv")
    n_real = min(300, len(df_mpm), len(df_dht), len(df_mq))
    engine_real = AnomalyEngine(min_samples_monitoring=10, min_samples_regression=20)
    real_flagged = 0
    real_faults = 0
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
        rep_anom = rep.get("anomaly") or {}
        if rep_anom.get("detected"):
            real_flagged += 1
        if rep_anom.get("is_hardware_fault"):
            real_faults += 1

    return {
        "synthetic_controlled": {
            "provenance": "SYNTHETIC",
            "n_eval_samples": len(y_true),
            "tp": tp,
            "fp": fp,
            "tn": tn,
            "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "false_positive_rate": round(fpr, 4),
            "false_negative_rate": round(fnr, 4),
            "pm_spike_detection_delay_samples": pm_detect_delay,
            "gas_spike_detection_delay_samples": gas_detect_delay,
            "timeline": timeline_records,
        },
        "real_recorded_replay": {
            "provenance": "REAL_RECORDED_DATA",
            "dataset": "dataset/{MPM_10,DHT22,MQ}_Dataset/session_1 (first 300 rows, unlabeled)",
            "n_samples": n_real,
            "anomaly_flagged_count": real_flagged,
            "sensor_fault_detected_count": real_faults,
            "note": "Unlabeled real recorded sensor session; accuracy is not reported because ground-truth anomaly labels do not exist.",
        },
    }


def evaluate_forecasting() -> Dict[str, Any]:
    fpath = REPO_ROOT / "data" / "historical_cache" / "airquality_bhubaneswar_2024-11-01_2024-12-05.json"
    with open(fpath, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    hourly = raw["hourly"]
    times = hourly["time"]
    pm25_all = hourly["pm2_5"]
    pm10_all = hourly["pm10"]

    records = []
    for t, p25, p10 in zip(times, pm25_all, pm10_all):
        if p25 is not None and p10 is not None:
            records.append({"timestamp": t, "PM2_5": float(p25), "PM10": float(p10)})

    # Walk-forward evaluation every 6 hours after 72h warmup, 6h horizon (6 hourly steps)
    ar_err_h: Dict[int, List[float]] = {1: [], 3: [], 6: []}
    pers_err_h: Dict[int, List[float]] = {1: [], 3: [], 6: []}
    sample_series: List[Dict[str, Any]] = []

    for idx in range(72, len(records) - 6, 6):
        history = records[max(0, idx - 72) : idx]
        resp = generate_forecast(
            records=history,
            channels=["PM2_5", "PM10"],
            node_id="bhubaneswar-ref",
            horizon_minutes=360,
            sampling_interval_minutes=60,
            min_history_points=24,
        )
        pm25_pred = next((c for c in resp.channels if c.channel == "PM2_5"), None)
        if not pm25_pred or len(pm25_pred.predicted_values) < 6:
            continue
        last_val = history[-1]["PM2_5"]
        for h in (1, 3, 6):
            actual = records[idx + h - 1]["PM2_5"]
            pred = pm25_pred.predicted_values[h - 1]
            ar_err_h[h].append(pred - actual)
            pers_err_h[h].append(last_val - actual)
        if len(sample_series) < 60:
            sample_series.append(
                {
                    "timestamp": records[idx]["timestamp"],
                    "actual_1h": round(records[idx]["PM2_5"], 2),
                    "ar_pred_1h": round(pm25_pred.predicted_values[0], 2),
                    "pers_pred_1h": round(last_val, 2),
                }
            )

    horizons = {}
    for h in (1, 3, 6):
        e_ar = ar_err_h[h]
        e_p = pers_err_h[h]
        horizons[f"{h}h"] = {
            "n": len(e_ar),
            "ar_mae": round(sum(abs(x) for x in e_ar) / len(e_ar), 3),
            "ar_rmse": round(math.sqrt(sum(x * x for x in e_ar) / len(e_ar)), 3),
            "persistence_mae": round(sum(abs(x) for x in e_p) / len(e_p), 3),
            "persistence_rmse": round(math.sqrt(sum(x * x for x in e_p) / len(e_p)), 3),
        }

    return {
        "provenance": "EXTERNAL_REFERENCE",
        "dataset": fpath.name,
        "target": "PM2_5 (hourly)",
        "horizons": horizons,
        "sample_series_1h": sample_series,
    }


# ---------------------------------------------------------------------------
# 3. Controlled Scenarios, End-to-End Performance, Reliability & Resources
# ---------------------------------------------------------------------------


def run_e2e_and_benchmarks() -> Dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="navos_p7_") as tmp:
        tmp_path = Path(tmp)
        os.environ["NAVOS_ENV"] = "development"
        os.environ["NAVOS_MANAGER_API_KEY"] = "phase7-bench-key"
        os.environ["NAVOS_TWILIO_MODE"] = "SIMULATED"
        os.environ["NAVOS_DATA_DIR"] = str(tmp_path / "data")
        os.environ["NAVOS_ARTIFACTS_DIR"] = str(SERVER_ROOT / "artifacts")
        os.environ["NAVOS_FORECAST_STORAGE_DIR"] = str(tmp_path / "forecast")
        os.environ["NAVOS_AQI_STORAGE_FILE"] = str(tmp_path / "aqi.json")
        os.environ["NAVOS_EMERGENCY_DB_PATH"] = str(tmp_path / "emergency.db")
        get_settings.cache_clear()

        headers = {"X-Navos-Manager-Key": "phase7-bench-key"}
        t_start = time.perf_counter()
        app = create_app()
        with TestClient(app) as client:
            startup_ms = (time.perf_counter() - t_start) * 1000.0

            # Register node, resident, caregiver, and offline actuator
            client.post(
                "/api/v1/emergency/nodes",
                json={"node_id": "p7-node-01", "node_name": "Bench Node", "location": "Lab"},
                headers=headers,
            )
            client.post(
                "/api/v1/emergency/residents",
                json={
                    "resident_id": "p7-res-01",
                    "full_name": "Benchmark Resident",
                    "associated_node_id": "p7-node-01",
                    "location": "Lab",
                    "consent_status": "GRANTED",
                },
                headers=headers,
            )
            client.post(
                "/api/v1/emergency/contacts",
                json={
                    "contact_id": "p7-c-1",
                    "resident_id": "p7-res-01",
                    "full_name": "Primary Caregiver",
                    "phone_number": "+919900112233",
                    "relationship": "Family",
                    "priority": 1,
                    "preferred_channels": ["SMS"],
                },
                headers=headers,
            )
            client.post(
                "/api/v1/actuators/heartbeat",
                json={
                    "actuator_id": "p7-esp32-01",
                    "associated_node_id": "p7-node-01",
                    "actuator_type": "EXHAUST_FAN",
                    "device_name": "Bench Fan",
                    "ip_address": "192.0.2.55",
                    "current_state": "OFF",
                },
                headers=headers,
            )

            # Controlled scenarios evaluation + latency measurement (40 normal readings)
            e2e_normal_ms: List[float] = []
            gen_clean = ScenarioGenerator(node_id="p7-node-01", scenario="clean_background", seed=SEED)
            for _ in range(40):
                payload = gen_clean.next_payload(10.0)
                t0 = time.perf_counter()
                r = client.post("/api/v1/nodes/p7-node-01/readings", json=payload)
                e2e_normal_ms.append((time.perf_counter() - t0) * 1000.0)
                assert r.status_code == 201

            # Check no false emergency events under clean background
            ev_after_clean = client.get("/api/v1/emergency/events", headers=headers).json()

            # Sudden gas hazard with mocked ESP32 HTTP 200 OK latency
            e2e_hazard_ms: List[float] = []
            mock_resp = httpx.Response(200, json={"status": "OK", "state": "ON"})
            with patch("app.emergency.actuator_service.httpx.AsyncClient.post", return_value=mock_resp):
                gen_gas = ScenarioGenerator(node_id="p7-node-01", scenario="gas_spike", seed=SEED)
                for _ in range(5):
                    payload = gen_gas.next_payload(10.0)
                    t0 = time.perf_counter()
                    r = client.post("/api/v1/nodes/p7-node-01/readings", json=payload)
                    e2e_hazard_ms.append((time.perf_counter() - t0) * 1000.0)
                    assert r.status_code == 201

            ev_after_gas = client.get("/api/v1/emergency/events", headers=headers).json()
            r_ntf = client.get("/api/v1/emergency/notifications", headers=headers)
            ntf_after_gas = r_ntf.json() if r_ntf.status_code == 200 else []

            # DB growth measurement
            db_path = tmp_path / "emergency.db"
            db_size_bytes = db_path.stat().st_size if db_path.exists() else 0

        rss_mb = get_process_rss_mb()
        cpu_s = round(time.process_time(), 3)
        get_settings.cache_clear()

        return {
            "provenance": "SYNTHETIC + MOCKED (SIMULATED notifications, loopback/mocked ESP32, Windows desktop)",
            "environment": {
                "platform": sys.platform,
                "python": sys.version.split()[0],
                "process_rss_mb": rss_mb,
                "process_cpu_time_s": cpu_s,
            },
            "startup_time_ms": round(startup_ms, 2),
            "e2e_normal_reading_latency": summarize_latencies(e2e_normal_ms),
            "e2e_hazard_reading_latency": summarize_latencies(e2e_hazard_ms),
            "clean_background_false_emergencies": len(ev_after_clean),
            "gas_hazard_events_created": len(ev_after_gas),
            "notifications_recorded": len(ntf_after_gas),
            "sqlite_db_size_bytes": db_size_bytes,
        }


def main() -> None:
    print("Running NavosEdge Phase 7 Experiments...")
    results = {
        "seed": SEED,
        "dataset_inventory": profile_datasets(),
        "gasnet_evaluation": evaluate_gasnet(),
        "source_classifier_evaluation": evaluate_source_classifier(),
        "anomaly_evaluation": evaluate_anomaly_engine(),
        "forecast_evaluation": evaluate_forecasting(),
        "e2e_and_benchmarks": run_e2e_and_benchmarks(),
    }
    out_file = OUT_DIR / "phase7_experiment_results.json"
    with open(out_file, "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    print(f"Saved results to {out_file}")


if __name__ == "__main__":
    main()
