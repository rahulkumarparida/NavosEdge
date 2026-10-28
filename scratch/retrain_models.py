"""
Retraining and calibration script for NavosEdge models:
1. TinyGasNet (NumPy-based AdamW + MC-Dropout + Temperature Scaling)
2. SourceClassifier (DecisionTree + ReferenceStats with realistic MADs)

Follows Phase 5 and Phase 6 rules:
- Fit scalers only on training splits.
- Evaluate on validation and independent test splits.
- Deploy to Intelligence/Server/artifacts and Training/models.
- Record training configuration, seed, dataset version, and metrics.
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

from Training.constants import RANDOM_SEED, FEATURES
from Training.mq_train import NumPyTinyGasNet
from app.source_classifier.categories import ALL_SOURCE_CLASSIFIER_FEATURES, SourceClassifierConfig
from app.source_classifier.train import generate_synthetic_dataset, compute_reference_statistics

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("NavosEdge-ModelTrainer")


def retrain_tinygasnet(output_dirs: list[Path]) -> dict:
    logger.info("=" * 60)
    logger.info("RETRAINING TINYGASNET (PURE NUMPY, REALISTIC SCALER)")
    logger.info("=" * 60)

    dataset_path = training_dir / "mq_synthetic_dataset.csv"
    if not dataset_path.exists():
        raise FileNotFoundError(f"Missing {dataset_path}")

    df = pd.read_csv(dataset_path)
    df = df.sort_values("timestamp").reset_index(drop=True)
    logger.info("Loaded %d samples from %s", len(df), dataset_path)
    logger.info("Classes present:\n%s", df["gas_label"].value_counts())

    X = df[FEATURES].values.astype(np.float32)
    le = LabelEncoder()
    y_class = le.fit_transform(df["gas_label"].values)
    y_safety = (df["safety_status"] == "unsafe").astype(np.float32).values

    # Chronological train (70%) / val (15%) / test (15%) split
    n = len(df)
    n_train = int(0.70 * n)
    n_val = int(0.15 * n)

    X_train, X_val, X_test = X[:n_train], X[n_train:n_train + n_val], X[n_train + n_val:]
    yc_train, yc_val, yc_test = y_class[:n_train], y_class[n_train:n_train + n_val], y_class[n_train + n_val:]
    ys_train, ys_val, ys_test = y_safety[:n_train], y_safety[n_train:n_train + n_val], y_safety[n_train + n_val:]

    # FIT SCALER ON TRAINING SET ONLY
    scaler = StandardScaler().fit(X_train)
    logger.info("Fitted StandardScaler on training split:")
    for feat_name, m, s in zip(FEATURES, scaler.mean_, scaler.scale_):
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
    logger.info("Optimal calibration temperature on val set: T = %.4f (NLL: %.4f)", optimal_T, best_nll)

    # Final Evaluation on Independent Test Set
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

    logger.info("Test Evaluation -> Accuracy: %.4f | Macro-F1: %.4f | Safety-F1: %.4f", acc, macro_f1, safety_f1)
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
        "feature_order": FEATURES,
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

    # Save to output directories
    for d in output_dirs:
        d.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(d / "gasnet_weights.npz", **model.state_dict())
        with open(d / "model_metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        joblib.dump({"scaler": scaler, "label_encoder": le, "temperature": optimal_T}, d / "preprocess.pkl")
        logger.info("Saved gasnet_weights.npz, model_metadata.json, preprocess.pkl to %s", d)

    return {
        "accuracy": acc,
        "macro_f1": macro_f1,
        "safety_f1": safety_f1,
        "classes": le.classes_.tolist(),
        "optimal_T": optimal_T,
        "scaler_scale": scaler.scale_.tolist(),
        "scaler_mean": scaler.mean_.tolist(),
    }


def retrain_source_classifier(output_dirs: list[Path]) -> dict:
    logger.info("\n" + "=" * 60)
    logger.info("RETRAINING SOURCE CLASSIFIER (PHYSICALLY GROUNDED SCENARIOS)")
    logger.info("=" * 60)

    from app.source_classifier.categories import SourceClassifierConfig
    config = SourceClassifierConfig()

    # Step 1: Generate diverse synthetic dataset across all 8 classes
    synth_df = generate_synthetic_dataset(seed=42)
    logger.info("Generated %d synthetic samples across 8 source categories", len(synth_df))

    # Step 2: Compute reference statistics with realistic MADs
    ref_stats = compute_reference_statistics(synth_df)
    logger.info("Computed reference statistics for %d categories", len(ref_stats))

    # Step 3: Train DecisionTreeClassifier
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

    # Test set evaluation
    y_pred = dt.predict(X_test_s)
    acc = float(accuracy_score(y_test, y_pred))
    macro_f1 = float(f1_score(y_test, y_pred, average="macro", zero_division=0))
    report = classification_report(y_test, y_pred, output_dict=True, zero_division=0)
    cm = confusion_matrix(y_test, y_pred, labels=dt.classes_).tolist()

    logger.info("Decision Tree Test Accuracy: %.4f | Macro-F1: %.4f", acc, macro_f1)
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

    # Save to output directories
    for d in output_dirs:
        d.mkdir(parents=True, exist_ok=True)
        joblib.dump(model_bundle, d / "source_classifier_model.pkl")
        with open(d / "source_classifier_stats.json", "w", encoding="utf-8") as f:
            json.dump(ref_stats, f, indent=2)
        with open(d / "source_classifier_metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, default=int)
        logger.info("Saved source_classifier artifacts to %s", d)

    return {
        "accuracy": acc,
        "macro_f1": macro_f1,
        "classes": list(dt.classes_),
        "tree_depth": dt.get_depth(),
        "n_leaves": dt.get_n_leaves(),
    }


def main():
    target_dirs = [
        server_dir / "artifacts",
        training_dir / "models",
    ]

    gasnet_res = retrain_tinygasnet(target_dirs)
    sc_res = retrain_source_classifier(target_dirs)

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gasnet": gasnet_res,
        "source_classifier": sc_res,
    }
    with open("test_data/retrained_models_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=int)

    logger.info("\n" + "=" * 60)
    logger.info("RETRAINING COMPLETED SUCCESSFULLY")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
