"""
NavosEdge Model Audit, Metric Reproduction & Data Independence Checker.
Reproduces all baseline and current metrics:
- GasNet 5-class evaluation (test split, canonical, unseen, perturbation)
- SourceClassifier 8-class evaluation (test split, canonical, unseen, perturbation)
- Forecasting AR vs. Persistence (Bhubaneswar 35-day dataset)
- Anomaly Detection (precision, recall, FPR, detection delay on injected faults)
- Artifact checksum and version verification
"""

import asyncio
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

# Paths
root_dir = Path(__file__).resolve().parents[1]
server_dir = root_dir / "Intelligence" / "Server"
training_dir = root_dir / "Training"

if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))
if str(training_dir) not in sys.path:
    sys.path.insert(0, str(training_dir))

from app.anomaly.engine import AnomalyEngine
from app.forecast.model import _ar_predict, _fit_ar
from app.schemas.sensor import SensorPayload
from app.services.numpy_inference import NumpyGasNetAdapter
from app.source_classifier.categories import ALL_SOURCE_CLASSIFIER_FEATURES
from app.source_classifier.classifier import SourceClassifier
from app.source_classifier.train import generate_synthetic_dataset
from Simulator.historical_generator import GenerationConfig, HistoricalDatasetGenerator
from Simulator.session import load_dataset
from Training.mq_train import NumPyTinyGasNet


def hash_file(p: Path) -> str:
    if not p.exists():
        return "MISSING"
    h = hashlib.sha256()
    h.update(p.read_bytes())
    return h.hexdigest()[:12]


def run_audit():
    print("=" * 80)
    print("NAVOSEDGE MODEL AUDIT, REPRODUCTION & VERIFICATION")
    print("=" * 80)

    artifacts_dir = (server_dir / "artifacts").resolve()
    backup_dir = (server_dir / "artifacts" / "backups" / "original_baseline").resolve()
    training_models_dir = (training_dir / "models").resolve()

    # ------------------------------------------------------------------
    # Step 1: Inspect Current Artifacts & Hashes
    # ------------------------------------------------------------------
    print("\n--- 1. ARTIFACT VERSION & CHECKSUM AUDIT ---")
    files_to_check = [
        "gasnet_weights.npz",
        "preprocess.pkl",
        "model_metadata.json",
        "source_classifier_model.pkl",
        "source_classifier_stats.json",
        "source_classifier_metadata.json",
    ]

    for f in files_to_check:
        h_active = hash_file(artifacts_dir / f)
        h_train = hash_file(training_models_dir / f)
        h_backup = hash_file(backup_dir / f)
        matches_train = (h_active == h_train)
        differs_backup = (h_active != h_backup)
        print(f"  {f:<32s}: Active={h_active} | Train={h_train} ({'MATCH' if matches_train else 'MISMATCH'}) | Backup={h_backup} ({'DIFFERENT' if differs_backup else 'IDENTICAL'})")

    with open(artifacts_dir / "model_metadata.json") as f:
        meta_gn = json.load(f)
    with open(artifacts_dir / "source_classifier_metadata.json") as f:
        meta_sc = json.load(f)

    print(f"\nTinyGasNet Active Metadata: version={meta_gn.get('model_version')}, classes={meta_gn.get('class_labels')}")
    print(f"SourceClassifier Active Metadata: version={meta_sc.get('version')}, classes={meta_sc.get('classes')}")

    # ------------------------------------------------------------------
    # Step 2: Reproduce TinyGasNet Test Metrics
    # ------------------------------------------------------------------
    print("\n--- 2. REPRODUCING TINYGASNET METRICS ---")
    from scratch.train_unified_models import generate_physically_grounded_gas_dataset
    df_gas = generate_physically_grounded_gas_dataset(n_samples=12000, seed=42)
    feature_cols = ["MQ2_V", "MQ9_V", "MQ135_V", "temperature_C", "humidity_pct"]

    X_all = df_gas[feature_cols].values.astype(np.float32)
    y_class_raw = df_gas["gas_label"].values

    # Test split is the last 15% (1800 samples)
    n_test = 1800
    X_test = X_all[-n_test:]
    y_test_raw = y_class_raw[-n_test:]

    # Load active model & scaler
    gn_active = NumpyGasNetAdapter(artifacts_dir=artifacts_dir)
    gn_active.load()
    gn_backup = NumpyGasNetAdapter(artifacts_dir=backup_dir)
    gn_backup.load()

    # Predict active
    preds_active = []
    for x in X_test:
        r = asyncio.run(gn_active.predict(x[0], x[1], x[2], x[3], x[4]))
        preds_active.append(r.gas_class)

    # Predict backup
    preds_backup = []
    for x in X_test:
        r = asyncio.run(gn_backup.predict(x[0], x[1], x[2], x[3], x[4]))
        preds_backup.append(r.gas_class)

    # Compute metrics for active
    gn_acc = accuracy_score(y_test_raw, preds_active)
    gn_bal_acc = balanced_accuracy_score(y_test_raw, preds_active)
    gn_macro_f1 = f1_score(y_test_raw, preds_active, average="macro", zero_division=0)
    gn_labels = sorted(list(set(y_test_raw)))
    gn_cm = confusion_matrix(y_test_raw, preds_active, labels=gn_labels)

    print(f"TinyGasNet Active Test (N=1800):")
    print(f"  Accuracy:         {gn_acc * 100:.2f}% (Report claimed: 99.22%)")
    print(f"  Balanced Accuracy:{gn_bal_acc * 100:.2f}%")
    print(f"  Macro-F1:         {gn_macro_f1 * 100:.2f}% (Report claimed: 99.10%)")
    print("  Per-Class Metrics:")
    for lbl in gn_labels:
        p = precision_score(y_test_raw, preds_active, labels=[lbl], average="micro", zero_division=0)
        rec = recall_score(y_test_raw, preds_active, labels=[lbl], average="micro", zero_division=0)
        f = f1_score(y_test_raw, preds_active, labels=[lbl], average="micro", zero_division=0)
        print(f"    {lbl:<10s}: Precision={p:.4f}, Recall={rec:.4f}, F1={f:.4f}")

    print("\n  Confusion Matrix (Labels: Alcohol, CO, CleanAir, LPG, Smoke):")
    print(gn_cm)

    # Backup performance on same test set
    gn_bk_acc = accuracy_score(y_test_raw, preds_backup)
    gn_bk_macro_f1 = f1_score(y_test_raw, preds_backup, average="macro", zero_division=0)
    print(f"\nTinyGasNet Backup Test on same N=1800 samples:")
    print(f"  Accuracy:         {gn_bk_acc * 100:.2f}%")
    print(f"  Macro-F1:         {gn_bk_macro_f1 * 100:.2f}%")
    unique_backup_preds = pd.Series(preds_backup).value_counts().to_dict()
    print(f"  Predicted Class Distribution: {unique_backup_preds}")

    # ------------------------------------------------------------------
    # Step 3: Reproduce SourceClassifier Test Metrics
    # ------------------------------------------------------------------
    print("\n--- 3. REPRODUCING SOURCE CLASSIFIER METRICS ---")
    synth_sc = generate_synthetic_dataset(seed=42)
    X_sc = synth_sc[ALL_SOURCE_CLASSIFIER_FEATURES].values.astype(np.float32)
    y_sc = synth_sc["label"].values

    from sklearn.model_selection import train_test_split
    X_sc_train, X_sc_test, y_sc_train, y_sc_test = train_test_split(
        X_sc, y_sc, test_size=0.20, random_state=42, stratify=y_sc
    )

    sc_bundle = joblib.load(artifacts_dir / "source_classifier_model.pkl")
    dt_active = sc_bundle["model"]
    scaler_sc = sc_bundle["scaler"]
    X_sc_test_s = scaler_sc.transform(X_sc_test)

    sc_preds_active = dt_active.predict(X_sc_test_s)
    sc_acc = accuracy_score(y_sc_test, sc_preds_active)
    sc_bal_acc = balanced_accuracy_score(y_sc_test, sc_preds_active)
    sc_macro_f1 = f1_score(y_sc_test, sc_preds_active, average="macro", zero_division=0)

    print(f"SourceClassifier Active Test (N={len(y_sc_test)}):")
    print(f"  Accuracy:         {sc_acc * 100:.2f}% (Report claimed: 82.78%)")
    print(f"  Balanced Accuracy:{sc_bal_acc * 100:.2f}%")
    print(f"  Macro-F1:         {sc_macro_f1 * 100:.2f}% (Report claimed: 82.33%)")

    # ------------------------------------------------------------------
    # Step 4: Reproduce Unseen & Perturbation Suites
    # ------------------------------------------------------------------
    print("\n--- 4. REPRODUCING UNSEEN & PERTURBATION SUITES ---")
    eval_dir = Path("test_data/unseen_eval")
    with open(eval_dir / "eval_unseen_combinations.json") as f:
        unseen_cases = json.load(f)
    with open(eval_dir / "eval_perturbations.json") as f:
        perturb_cases = json.load(f)

    sc_active = SourceClassifier(artifacts_dir=artifacts_dir)
    sc_active.load()
    sc_backup = SourceClassifier(artifacts_dir=backup_dir)
    sc_backup.load()

    u_gn_act, u_gn_bk, u_sc_act, u_sc_bk = 0, 0, 0, 0
    for c in unseen_cases:
        p = SensorPayload.model_validate(c["payload"])
        r_gn_act = asyncio.run(gn_active.predict(p.gas_sensors.MQ2.voltage_V, p.gas_sensors.MQ9.voltage_V, p.gas_sensors.MQ135.voltage_V, p.environment.temperature_C, p.environment.humidity_pct))
        r_gn_bk = asyncio.run(gn_backup.predict(p.gas_sensors.MQ2.voltage_V, p.gas_sensors.MQ9.voltage_V, p.gas_sensors.MQ135.voltage_V, p.environment.temperature_C, p.environment.humidity_pct))
        r_sc_act = sc_active.classify(p)
        r_sc_bk = sc_backup.classify(p)

        if r_gn_act.gas_class == c["expected_gas"]: u_gn_act += 1
        if r_gn_bk.gas_class == c["expected_gas"]: u_gn_bk += 1
        if r_sc_act.get("top_source") == c["expected_source"]: u_sc_act += 1
        if r_sc_bk.get("top_source") == c["expected_source"]: u_sc_bk += 1

    print(f"Unseen Scenarios Score (N={len(unseen_cases)}):")
    print(f"  GasNet:           Backup = {u_gn_bk}/{len(unseen_cases)} ({u_gn_bk/len(unseen_cases)*100:.1f}%) | Active = {u_gn_act}/{len(unseen_cases)} ({u_gn_act/len(unseen_cases)*100:.1f}%)")
    print(f"  SourceClassifier: Backup = {u_sc_bk}/{len(unseen_cases)} ({u_sc_bk/len(unseen_cases)*100:.1f}%) | Active = {u_sc_act}/{len(unseen_cases)} ({u_sc_act/len(unseen_cases)*100:.1f}%)")

    p_act, p_bk = 0, 0
    for c in perturb_cases:
        p = SensorPayload.model_validate(c["payload"])
        r_gn_act = asyncio.run(gn_active.predict(p.gas_sensors.MQ2.voltage_V, p.gas_sensors.MQ9.voltage_V, p.gas_sensors.MQ135.voltage_V, p.environment.temperature_C, p.environment.humidity_pct))
        r_gn_bk = asyncio.run(gn_backup.predict(p.gas_sensors.MQ2.voltage_V, p.gas_sensors.MQ9.voltage_V, p.gas_sensors.MQ135.voltage_V, p.environment.temperature_C, p.environment.humidity_pct))
        r_sc_act = sc_active.classify(p)
        r_sc_bk = sc_backup.classify(p)

        ok_act = (r_gn_act.gas_class == c["expected_gas"]) and (r_sc_act.get("top_source") == c["expected_source"])
        ok_bk = (r_gn_bk.gas_class == c["expected_gas"]) and (r_sc_bk.get("top_source") == c["expected_source"])
        if ok_act: p_act += 1
        if ok_bk: p_bk += 1

    print(f"Perturbation Robustness (N={len(perturb_cases)}):")
    print(f"  Combined: Backup = {p_bk}/{len(perturb_cases)} ({p_bk/len(perturb_cases)*100:.1f}%) | Active = {p_act}/{len(perturb_cases)} ({p_act/len(perturb_cases)*100:.1f}%)")

    # -------------------------------------------------------------
    # Step 5: Reproduce Forecasting Comparison (35-Day Dataset)
    # -------------------------------------------------------------
    print("\n--- 5. REPRODUCING FORECASTING METRICS (35-DAY DATASET) ---")
    dataset_records = load_dataset(Path("test_data/historical_35d.jsonl"))
    pm25_s = [r["particulate_matter"]["PM2_5"] for r in dataset_records if "particulate_matter" in r]
    pm10_s = [r["particulate_matter"]["PM10"] for r in dataset_records if "particulate_matter" in r]

    split = int(len(pm25_s) * 0.8)
    train25, test25 = pm25_s[:split], pm25_s[split:]
    train10, test10 = pm10_s[:split], pm10_s[split:]

    c25, b25 = _fit_ar(train25, order=3)
    c10, b10 = _fit_ar(train10, order=3)

    for h_name, h_steps in [("15m (3 steps)", 3), ("30m (6 steps)", 6), ("60m (12 steps)", 12)]:
        def eval_forecast(train_vals, test_vals, coeffs, intercept, steps):
            acts, preds_p, preds_ar = [], [], []
            for s in range(len(test_vals) - steps):
                hist = list(train_vals) + list(test_vals[:s])
                preds_p.append(hist[-1])
                acts.append(test_vals[s + steps])
                preds_ar.append(_ar_predict(coeffs, intercept, hist, steps)[-1])
            p_mae = sum(abs(p - a) for p, a in zip(preds_p, acts)) / len(acts)
            p_rmse = math.sqrt(sum((p - a)**2 for p, a in zip(preds_p, acts)) / len(acts))
            ar_mae = sum(abs(p - a) for p, a in zip(preds_ar, acts)) / len(acts)
            ar_rmse = math.sqrt(sum((p - a)**2 for p, a in zip(preds_ar, acts)) / len(acts))
            return p_mae, p_rmse, ar_mae, ar_rmse

        p25_mae, p25_rmse, ar25_mae, ar25_rmse = eval_forecast(train25, test25, c25, b25, h_steps)
        p10_mae, p10_rmse, ar10_mae, ar10_rmse = eval_forecast(train10, test10, c10, b10, h_steps)
        print(f"  Horizon {h_name}:")
        print(f"    PM2.5 -> Persistence MAE={p25_mae:.2f}, RMSE={p25_rmse:.2f} | Damped AR(3) MAE={ar25_mae:.2f}, RMSE={ar25_rmse:.2f} [{'WIN' if ar25_mae <= p25_mae else 'LOSS'}]")
        print(f"    PM10  -> Persistence MAE={p10_mae:.2f}, RMSE={p10_rmse:.2f} | Damped AR(3) MAE={ar10_mae:.2f}, RMSE={ar10_rmse:.2f} [{'WIN' if ar10_mae <= p10_mae else 'LOSS'}]")

    # -------------------------------------------------------------
    # Step 6: Anomaly Detection Evaluation on Injected Faults
    # -------------------------------------------------------------
    print("\n--- 6. ANOMALY DETECTION EVALUATION (PRECISION, RECALL, FPR, DELAY) ---")
    gen_config = GenerationConfig(
        node_id="eval-node-faults",
        days=35,
        sampling_interval_seconds=300.0,
        seed=42,
        start_date="2024-09-01",
        location="bhubaneswar",
        inject_faults=True,
    )
    generator = HistoricalDatasetGenerator(gen_config)
    fault_records = generator.generate_all()

    engine = AnomalyEngine()
    y_true_fault = []
    y_pred_anomaly = []
    detection_delays = []
    current_fault_start = None

    for i, rec in enumerate(fault_records):
        prov = rec.get("provenance", {})
        fault_type = prov.get("fault")
        is_ground_truth_fault = (fault_type is not None and fault_type != "warmup")

        # Track start of fault episode
        if is_ground_truth_fault and current_fault_start is None:
            current_fault_start = rec["timestamp"]
        elif not is_ground_truth_fault:
            current_fault_start = None

        res = engine.analyse("eval-node-faults", rec)
        anom_dict = res.get("anomaly", {})
        detected = anom_dict.get("detected", False)
        severity = anom_dict.get("severity", "NONE")
        is_flagged = (detected or severity in {"MEDIUM", "HIGH", "CRITICAL"})

        y_true_fault.append(is_ground_truth_fault)
        y_pred_anomaly.append(is_flagged)

        if is_ground_truth_fault and is_flagged and current_fault_start is not None:
            t_start = datetime.fromisoformat(current_fault_start)
            t_now = datetime.fromisoformat(rec["timestamp"])
            delay_sec = (t_now - t_start).total_seconds()
            detection_delays.append(delay_sec / 60.0)

    tp = sum(t and p for t, p in zip(y_true_fault, y_pred_anomaly))
    fp = sum(not t and p for t, p in zip(y_true_fault, y_pred_anomaly))
    tn = sum(not t and not p for t, p in zip(y_true_fault, y_pred_anomaly))
    fn = sum(t and not p for t, p in zip(y_true_fault, y_pred_anomaly))

    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec_rate = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    f1_anom = 2 * prec * rec_rate / (prec + rec_rate) if (prec + rec_rate) > 0 else 0.0
    mean_delay = np.mean(detection_delays) if detection_delays else 0.0

    print(f"Anomaly Detection Metrics (Total Readings = {len(fault_records)}):")
    print(f"  True Positives:  {tp}")
    print(f"  False Positives: {fp}")
    print(f"  True Negatives:  {tn}")
    print(f"  False Negatives: {fn}")
    print(f"  Precision:       {prec * 100:.2f}%")
    print(f"  Recall:          {rec_rate * 100:.2f}%")
    print(f"  False Pos. Rate: {fpr * 100:.2f}%")
    print(f"  F1 Score:        {f1_anom * 100:.2f}%")
    print(f"  Mean Delay:      {mean_delay:.1f} minutes")

    print("\nAUDIT AND REPRODUCTION RUN COMPLETE.")


if __name__ == "__main__":
    run_audit()
