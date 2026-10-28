"""
NavosEdge Unified Model Retraining & Calibration Pipeline.
Aligns TinyGasNet and SourceClassifier with the unified physical sensor representations
and realistic ambient environmental ranges (15C - 42C, 25% - 92% RH).

Phases 5 & 6 Compliant:
- Scalers fitted strictly on training data.
- Validation sets used for calibration / hyperparameter tuning.
- Untouched test sets used for final evaluation.
- All artifact paths strictly resolved to absolute paths.
"""

from __future__ import annotations

import json
import logging
import math
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

# Setup paths
root_dir = Path(__file__).resolve().parents[1]
server_dir = root_dir / "Intelligence" / "Server"
training_dir = root_dir / "Training"

if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))
if str(training_dir) not in sys.path:
    sys.path.insert(0, str(training_dir))

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import classification_report, confusion_matrix, f1_score, accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

from Training.mq_train import NumPyTinyGasNet
from app.source_classifier.categories import ALL_SOURCE_CLASSIFIER_FEATURES, SourceClassifierConfig
from app.source_classifier.train import generate_synthetic_dataset, compute_reference_statistics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("NavosEdge-ModelTrainer")


def generate_physically_grounded_gas_dataset(n_samples: int = 12000, seed: int = 42) -> pd.DataFrame:
    """
    Generate physically realistic gas sensor dataset matching the circuit
    and environmental parameters used throughout NavosEdge.
    
    Classes:
    - CleanAir: Nominal baseline (0.6 - 1.1V across all MQ sensors)
    - Smoke: Strong MQ2 response (1.8 - 3.8V), moderate MQ135 (1.6 - 2.8V)
    - Alcohol: Strong MQ135 response (1.8 - 3.5V), low/moderate MQ2 & MQ9
    - CO: Strong MQ9 response (1.6 - 3.2V), moderate MQ2
    - LPG: Strong MQ2 and MQ9 response (1.6 - 3.0V), low MQ135
    """
    rng = np.random.default_rng(seed)

    profiles = {
        "CleanAir": {
            "weight": 0.35, "safe": True,
            "mq2": (0.80, 0.12), "mq9": (0.70, 0.10), "mq135": (0.75, 0.12),
        },
        "Smoke": {
            "weight": 0.20, "safe": False,
            "mq2": (2.65, 0.38), "mq9": (1.75, 0.28), "mq135": (2.25, 0.35),
        },
        "Alcohol": {
            "weight": 0.15, "safe": False,
            "mq2": (0.95, 0.15), "mq9": (0.85, 0.12), "mq135": (2.75, 0.38),
        },
        "CO": {
            "weight": 0.15, "safe": False,
            "mq2": (1.15, 0.18), "mq9": (2.60, 0.38), "mq135": (1.30, 0.20),
        },
        "LPG": {
            "weight": 0.15, "safe": False,
            "mq2": (2.40, 0.35), "mq9": (2.10, 0.32), "mq135": (1.20, 0.20),
        },
    }

    classes = list(profiles.keys())
    weights = [profiles[c]["weight"] for c in classes]

    rows = []
    base_t = datetime(2024, 9, 1, 0, 0, 0, tzinfo=timezone.utc)

    for i in range(n_samples):
        gas = rng.choice(classes, p=weights)
        prof = profiles[gas]

        # Realistic Indian climate variation: Temp 15C - 42C, Humidity 25% - 92%
        temp = float(np.clip(rng.normal(28.0, 6.0), 14.0, 44.0))
        hum = float(np.clip(rng.normal(58.0, 15.0), 22.0, 94.0))

        # Thermal and humidity drift coefficients on sensor baseline
        temp_factor = 1.0 + 0.003 * (28.0 - temp)
        hum_factor = 1.0 + 0.002 * (hum - 58.0)
        env_factor = temp_factor * hum_factor

        # Sensor response voltages
        v2 = float(np.clip(rng.normal(prof["mq2"][0], prof["mq2"][1]) * env_factor, 0.05, 4.95))
        v9 = float(np.clip(rng.normal(prof["mq9"][0], prof["mq9"][1]) * env_factor, 0.05, 4.95))
        v135 = float(np.clip(rng.normal(prof["mq135"][0], prof["mq135"][1]) * env_factor, 0.05, 4.95))

        # Sensor noise (+- 2%)
        v2 = float(np.clip(v2 + rng.normal(0, 0.02 * v2), 0.02, 4.98))
        v9 = float(np.clip(v9 + rng.normal(0, 0.02 * v9), 0.02, 4.98))
        v135 = float(np.clip(v135 + rng.normal(0, 0.02 * v135), 0.02, 4.98))

        # Safety determination
        is_unsafe = (gas != "CleanAir") and (v2 > 1.6 or v9 > 1.6 or v135 > 1.8)
        safety_status = "unsafe" if is_unsafe else "safe"

        ts = (base_t + pd.Timedelta(seconds=i * 60)).isoformat()
        rows.append({
            "sample_id": i + 1,
            "timestamp": ts,
            "MQ2_V": round(v2, 4),
            "MQ9_V": round(v9, 4),
            "MQ135_V": round(v135, 4),
            "temperature_C": round(temp, 2),
            "humidity_pct": round(hum, 2),
            "gas_label": gas,
            "safety_status": safety_status,
        })

    return pd.DataFrame(rows)


def retrain_tinygasnet(output_dirs: list[Path]) -> dict:
    logger.info("=" * 60)
    logger.info("RETRAINING TINYGASNET (PHYSICALLY GROUNDED REPRESENTATION)")
    logger.info("=" * 60)

    df = generate_physically_grounded_gas_dataset(n_samples=12000, seed=42)
    feature_cols = ["MQ2_V", "MQ9_V", "MQ135_V", "temperature_C", "humidity_pct"]

    X = df[feature_cols].values.astype(np.float32)
    le = LabelEncoder()
    y_class = le.fit_transform(df["gas_label"].values)
    y_safety = (df["safety_status"] == "unsafe").astype(np.float32).values

    # Chronological 70% Train, 15% Val, 15% Test split
    n = len(df)
    n_train = int(0.70 * n)
    n_val = int(0.15 * n)

    X_train, X_val, X_test = X[:n_train], X[n_train:n_train + n_val], X[n_train + n_val:]
    yc_train, yc_val, yc_test = y_class[:n_train], y_class[n_train:n_train + n_val], y_class[n_train + n_val:]
    ys_train, ys_val, ys_test = y_safety[:n_train], y_safety[n_train:n_train + n_val], y_safety[n_train + n_val:]

    # FIT SCALER ON TRAINING SET ONLY
    scaler = StandardScaler().fit(X_train)
    logger.info("Fitted StandardScaler on training split:")
    for feat_name, m, s in zip(feature_cols, scaler.mean_, scaler.scale_):
        logger.info("  %s: mean=%.4f, std=%.4f", feat_name, m, s)

    X_train_s = scaler.transform(X_train).astype(np.float32)
    X_val_s = scaler.transform(X_val).astype(np.float32)
    X_test_s = scaler.transform(X_test).astype(np.float32)

    model = NumPyTinyGasNet(n_features=5, n_classes=len(le.classes_), hidden1=32, hidden2=16)
    model.fit(X_train_s, yc_train, ys_train, X_val_s, yc_val, ys_val, epochs=50, lr=0.005, batch_size=64)

    # Temperature Scaling on Validation Set
    _, _, val_logits_c, _ = model.forward(X_val_s, train=False)
    best_T = 1.0
    best_nll = float("inf")
    for T_cand in np.linspace(0.2, 5.0, 97):
        scaled_c = val_logits_c / T_cand
        exp_c = np.exp(scaled_c - np.max(scaled_c, axis=-1, keepdims=True))
        probs_c = exp_c / np.sum(exp_c, axis=-1, keepdims=True)
        nll = -np.mean(np.log(probs_c[np.arange(len(X_val_s)), yc_val] + 1e-12))
        if nll < best_nll:
            best_nll = nll
            best_T = float(T_cand)
    optimal_T = float(best_T)
    logger.info("Optimal calibration temperature on val set: T = %.4f", optimal_T)

    # Evaluate on untouched test set
    _, _, test_logits_c, test_logit_s = model.forward(X_test_s, train=False)
    scaled_test = test_logits_c / optimal_T
    pc = scaled_test.argmax(axis=1)
    prob_s = 1.0 / (1.0 + np.exp(-np.clip(test_logit_s, -15.0, 15.0)))
    ps = (prob_s > 0.5).astype(int)

    acc = float(accuracy_score(yc_test, pc))
    macro_f1 = float(f1_score(yc_test, pc, average="macro", zero_division=0))
    safety_f1 = float(f1_score(ys_test, ps, zero_division=0))
    report_dict = classification_report(yc_test, pc, target_names=le.classes_, output_dict=True, zero_division=0)
    cm = confusion_matrix(yc_test, pc).tolist()

    logger.info("TinyGasNet Test -> Accuracy: %.4f | Macro-F1: %.4f | Safety-F1: %.4f", acc, macro_f1, safety_f1)
    logger.info("\n%s", classification_report(yc_test, pc, target_names=le.classes_, zero_division=0))

    metadata = {
        "model_version": datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S"),
        "architecture": {
            "n_features": 5,
            "hidden1": 32,
            "hidden2": 16,
            "n_classes": len(le.classes_),
            "p_drop": 0.1,
        },
        "feature_order": feature_cols,
        "class_labels": le.classes_.tolist(),
        "calibration_temperature": optimal_T,
        "preprocessing": {
            "scaler_mean": scaler.mean_.tolist(),
            "scaler_scale": scaler.scale_.tolist(),
        },
        "evaluation": {
            "accuracy": acc,
            "macro_f1": macro_f1,
            "safety_f1": safety_f1,
            "n_test_samples": len(yc_test),
            "confusion_matrix": cm,
            "per_class": report_dict,
        },
        "expected_input_ranges": {
            "MQ2_V": [0.0, 5.0],
            "MQ9_V": [0.0, 5.0],
            "MQ135_V": [0.0, 5.0],
            "temperature_C": [-35.0, 80.0],
            "humidity_pct": [0.0, 100.0],
        },
        "export_timestamp": datetime.now(timezone.utc).isoformat(),
    }

    for d in output_dirs:
        d.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(d / "gasnet_weights.npz", **model.state_dict())
        with open(d / "model_metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, default=int)
        joblib.dump({"scaler": scaler, "label_encoder": le, "temperature": optimal_T}, d / "preprocess.pkl")
        logger.info("Saved TinyGasNet artifacts to %s", d)

    return {
        "accuracy": acc,
        "macro_f1": macro_f1,
        "safety_f1": safety_f1,
        "classes": le.classes_.tolist(),
        "optimal_T": optimal_T,
    }


def retrain_source_classifier(output_dirs: list[Path]) -> dict:
    logger.info("\n" + "=" * 60)
    logger.info("RETRAINING SOURCE CLASSIFIER (8 URBAN SCENARIO CLASSES)")
    logger.info("=" * 60)

    # Step 1: Generate diverse multi-class dataset
    synth_df = generate_synthetic_dataset(seed=42)
    ref_stats = compute_reference_statistics(synth_df)

    X = synth_df[ALL_SOURCE_CLASSIFIER_FEATURES].values.astype(np.float32)
    y = synth_df["label"].values

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    # Fit scaler on training set only
    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train)
    X_test_s = scaler.transform(X_test)

    dt = DecisionTreeClassifier(
        max_depth=8,
        min_samples_split=10,
        min_samples_leaf=5,
        class_weight="balanced",
        random_state=42,
    )
    dt.fit(X_train_s, y_train)

    y_pred = dt.predict(X_test_s)
    acc = float(accuracy_score(y_test, y_pred))
    macro_f1 = float(f1_score(y_test, y_pred, average="macro", zero_division=0))
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_test, y_pred, labels=dt.classes_).tolist()

    logger.info("Source Classifier Test -> Accuracy: %.4f | Macro-F1: %.4f", acc, macro_f1)
    logger.info("\n%s", classification_report(y_test, y_pred, zero_division=0))

    model_bundle = {
        "model": dt,
        "scaler": scaler,
        "class_names": list(dt.classes_),
        "feature_names": ALL_SOURCE_CLASSIFIER_FEATURES,
    }

    metadata = {
        "version": f"1.1.0-retrained-{datetime.now(timezone.utc).strftime('%Y%m%d')}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_type": "DecisionTreeClassifier",
        "training_data": "SYNTHETIC — multi-scenario urban environmental modeling",
        "classes": list(dt.classes_),
        "features": ALL_SOURCE_CLASSIFIER_FEATURES,
        "evaluation": {
            "accuracy": acc,
            "macro_f1": macro_f1,
            "tree_depth": dt.get_depth(),
            "n_leaves": dt.get_n_leaves(),
            "n_train": len(X_train),
            "n_test": len(X_test),
            "confusion_matrix": cm,
            "per_class": report,
        },
        "config": {
            "max_depth": 8,
            "min_samples_split": 10,
            "min_samples_leaf": 5,
        },
    }

    for d in output_dirs:
        d.mkdir(parents=True, exist_ok=True)
        joblib.dump(model_bundle, d / "source_classifier_model.pkl")
        with open(d / "source_classifier_stats.json", "w", encoding="utf-8") as f:
            json.dump(ref_stats, f, indent=2, default=int)
        with open(d / "source_classifier_metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, default=int)
        logger.info("Saved SourceClassifier artifacts to %s", d)

    return {
        "accuracy": acc,
        "macro_f1": macro_f1,
        "classes": list(dt.classes_),
    }


def main():
    target_dirs = [
        (server_dir / "artifacts").resolve(),
        (training_dir / "models").resolve(),
    ]

    gasnet_res = retrain_tinygasnet(target_dirs)
    sc_res = retrain_source_classifier(target_dirs)

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gasnet": gasnet_res,
        "source_classifier": sc_res,
    }
    with open("test_data/unified_retraining_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=int)

    logger.info("UNIFIED RETRAINING AND DEPLOYMENT COMPLETE")


if __name__ == "__main__":
    main()
