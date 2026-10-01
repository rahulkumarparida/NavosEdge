#!/usr/bin/env python3
"""
NavosEdge Phase 12 — PyTorch-Free Retraining & Model Update Pipeline

Complete model refresh pipeline using the dataset in `dataset/`:
1. Validate dataset CSVs (DHT22, MPM10, MQ).
2. Detect missing/invalid values and handle them safely.
3. Chronologically align sensor streams using timestamps.
4. Build final feature representations for existing models.
5. Backup previous artifacts before replacing.
6. Retrain TinyGasNet (Anomaly Model) using pure NumPy (AdamW 2-head MLP) with temperature scaling.
7. Calibrate Source Classifier range bounds & Decision Tree on dataset distributions.
8. Prime chronological history for Forecast Model and verify 48h policy.
9. Evaluate trained models on test set.
10. Deploy new artifacts to expected locations (`artifacts/`, `models/`).
11. Verify automatic artifact loading without PyTorch or code changes.

Usage:
    python Training/retrain.py
"""

import argparse
import glob
import json
import logging
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.metrics import classification_report, f1_score, accuracy_score
from sklearn.tree import DecisionTreeClassifier
from sklearn.model_selection import train_test_split

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("NavosEdge-Retrain")

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
DATASET_DIR = PROJECT_ROOT / "dataset"
ARTIFACTS_DIR = PROJECT_ROOT / "Intelligence" / "Server" / "artifacts"
SERVER_MODELS_DIR = PROJECT_ROOT / "Intelligence" / "Server" / "models"
TRAINING_MODELS_DIR = PROJECT_ROOT / "Training" / "models"
READINGS_DIR = PROJECT_ROOT / "Intelligence" / "Server" / "data" / "readings" / "uno-q-001"

# ------------------------------------------------------------------
# Reproducibility
# ------------------------------------------------------------------
SEED = 42
np.random.seed(SEED)

# ------------------------------------------------------------------
# Pure NumPy TinyGasNet Implementation (PyTorch-Free)
# ------------------------------------------------------------------
class NumPyTinyGasNet:
    """
    Pure NumPy implementation of TinyGasNet 2-Head MLP.
    Zero PyTorch dependency required for training or inference.
    """

    def __init__(self, n_features: int = 5, n_classes: int = 5, hidden1: int = 32, hidden2: int = 16, p_drop: float = 0.1):
        self.n_features = n_features
        self.n_classes = n_classes
        self.hidden1 = hidden1
        self.hidden2 = hidden2
        self.p_drop = p_drop

        # He initialization for ReLU activations
        rng = np.random.RandomState(SEED)
        self.W1 = (rng.randn(hidden1, n_features) * np.sqrt(2.0 / n_features)).astype(np.float32)
        self.b1 = np.zeros(hidden1, dtype=np.float32)

        self.W2 = (rng.randn(hidden2, hidden1) * np.sqrt(2.0 / hidden1)).astype(np.float32)
        self.b2 = np.zeros(hidden2, dtype=np.float32)

        self.Wc = (rng.randn(n_classes, hidden2) * np.sqrt(2.0 / hidden2)).astype(np.float32)
        self.bc = np.zeros(n_classes, dtype=np.float32)

        self.Ws = (rng.randn(1, hidden2) * np.sqrt(2.0 / hidden2)).astype(np.float32)
        self.bs = np.zeros(1, dtype=np.float32)

    def forward(self, x: np.ndarray, train: bool = False, rng: np.random.RandomState = None):
        h1 = np.maximum(0, x @ self.W1.T + self.b1)
        if train and self.p_drop > 0:
            mask1 = (rng.rand(*h1.shape) >= self.p_drop).astype(np.float32) / (1.0 - self.p_drop)
            h1 = h1 * mask1

        h2 = np.maximum(0, h1 @ self.W2.T + self.b2)
        if train and self.p_drop > 0:
            mask2 = (rng.rand(*h2.shape) >= self.p_drop).astype(np.float32) / (1.0 - self.p_drop)
            h2 = h2 * mask2

        logits_c = h2 @ self.Wc.T + self.bc
        logit_s = (h2 @ self.Ws.T + self.bs).squeeze(-1)
        return h1, h2, logits_c, logit_s

    def state_dict(self) -> Dict[str, np.ndarray]:
        return {
            "fc1.weight": self.W1.copy(),
            "fc1.bias": self.b1.copy(),
            "fc2.weight": self.W2.copy(),
            "fc2.bias": self.b2.copy(),
            "class_head.weight": self.Wc.copy(),
            "class_head.bias": self.bc.copy(),
            "safety_head.weight": self.Ws.copy(),
            "safety_head.bias": self.bs.copy(),
        }

    def load_state_dict(self, state_dict: Dict[str, np.ndarray]):
        self.W1 = state_dict["fc1.weight"].astype(np.float32)
        self.b1 = state_dict["fc1.bias"].astype(np.float32)
        self.W2 = state_dict["fc2.weight"].astype(np.float32)
        self.b2 = state_dict["fc2.bias"].astype(np.float32)
        self.Wc = state_dict["class_head.weight"].astype(np.float32)
        self.bc = state_dict["class_head.bias"].astype(np.float32)
        self.Ws = state_dict["safety_head.weight"].astype(np.float32)
        self.bs = state_dict["safety_head.bias"].astype(np.float32)

    def fit(self, X_train: np.ndarray, yc_train: np.ndarray, ys_train: np.ndarray,
            X_val: np.ndarray, yc_val: np.ndarray, ys_val: np.ndarray,
            epochs: int = 50, lr: float = 0.005, batch_size: int = 64, weight_decay: float = 1e-4):
        rng = np.random.RandomState(SEED)

        # Class weights & Pos weights for imbalance handling
        counts = np.bincount(yc_train, minlength=self.n_classes)
        cw = 1.0 / np.maximum(counts, 1)
        class_weights = (cw / cw.sum() * len(cw)).astype(np.float32)

        pos = ys_train.sum()
        neg = len(ys_train) - pos
        pos_weight = float(neg / max(pos, 1.0))

        # AdamW optimizer moments
        m = {k: np.zeros_like(v) for k, v in self.state_dict().items()}
        v = {k: np.zeros_like(val) for k, val in self.state_dict().items()}
        beta1, beta2, eps = 0.9, 0.999, 1e-8
        t_step = 0

        best_loss = float("inf")
        best_weights = None

        n = len(X_train)
        for epoch in range(1, epochs + 1):
            indices = rng.permutation(n)
            for i in range(0, n, batch_size):
                idx = indices[i:i + batch_size]
                xb, ycb, ysb = X_train[idx], yc_train[idx], ys_train[idx]
                batch_len = len(xb)

                # Forward pass
                h1, h2, logits_c, logit_s = self.forward(xb, train=True, rng=rng)

                # Softmax & Sigmoid
                exp_c = np.exp(logits_c - np.max(logits_c, axis=-1, keepdims=True))
                probs_c = exp_c / np.sum(exp_c, axis=-1, keepdims=True)
                prob_s = 1.0 / (1.0 + np.exp(-np.clip(logit_s, -15.0, 15.0)))

                # Weighted Cross-Entropy gradient (Class head)
                dlogits_c = probs_c.copy()
                dlogits_c[np.arange(batch_len), ycb] -= 1.0
                dlogits_c *= class_weights[ycb][:, None]
                dlogits_c /= batch_len

                # Weighted BCE gradient (Safety head)
                w_s = np.where(ysb == 1.0, pos_weight, 1.0)
                dlogit_s = ((prob_s - ysb) * w_s / batch_len * 0.5)

                # Backpropagation
                dWc = dlogits_c.T @ h2
                dbc = np.sum(dlogits_c, axis=0)

                dWs = dlogit_s[:, None].T @ h2
                dbs = np.sum(dlogit_s, axis=0, keepdims=True)

                dh2 = dlogits_c @ self.Wc + dlogit_s[:, None] @ self.Ws
                dh2[h2 <= 0] = 0.0

                dW2 = dh2.T @ h1
                db2 = np.sum(dh2, axis=0)

                dh1 = dh2 @ self.W2
                dh1[h1 <= 0] = 0.0

                dW1 = dh1.T @ xb
                db1 = np.sum(dh1, axis=0)

                grads = {
                    "fc1.weight": dW1, "fc1.bias": db1,
                    "fc2.weight": dW2, "fc2.bias": db2,
                    "class_head.weight": dWc, "class_head.bias": dbc,
                    "safety_head.weight": dWs, "safety_head.bias": dbs,
                }

                # AdamW Update
                t_step += 1
                curr_state = self.state_dict()
                for key in grads:
                    g = grads[key]
                    w = curr_state[key]
                    # Weight decay step
                    g += weight_decay * w
                    m[key] = beta1 * m[key] + (1.0 - beta1) * g
                    v[key] = beta2 * v[key] + (1.0 - beta2) * (g ** 2)
                    m_hat = m[key] / (1.0 - beta1 ** t_step)
                    v_hat = v[key] / (1.0 - beta2 ** t_step)
                    w -= lr * m_hat / (np.sqrt(v_hat) + eps)
                    curr_state[key] = w
                self.load_state_dict(curr_state)

            # Validation loss evaluation
            _, _, val_logits_c, val_logit_s = self.forward(X_val, train=False)
            val_exp_c = np.exp(val_logits_c - np.max(val_logits_c, axis=-1, keepdims=True))
            val_probs_c = val_exp_c / np.sum(val_exp_c, axis=-1, keepdims=True)
            val_prob_s = 1.0 / (1.0 + np.exp(-np.clip(val_logit_s, -15.0, 15.0)))

            v_loss_c = -np.mean(np.log(val_probs_c[np.arange(len(X_val)), yc_val] + 1e-12))
            v_loss_s = -np.mean(ys_val * np.log(val_prob_s + 1e-12) + (1 - ys_val) * np.log(1 - val_prob_s + 1e-12))
            val_loss = v_loss_c + 0.5 * v_loss_s

            if val_loss < best_loss:
                best_loss = val_loss
                best_weights = self.state_dict()

        if best_weights:
            self.load_state_dict(best_weights)


# ------------------------------------------------------------------
# Step 1: Load, Validate & Chronologically Align Dataset
# ------------------------------------------------------------------
def load_and_validate_dataset() -> pd.DataFrame:
    logger.info("Step 1: Inspecting & validating dataset CSV files...")

    # Load DHT22 files
    dht_files = sorted(DATASET_DIR.glob("DHT22_Dataset/*.csv"))
    if not dht_files:
        raise FileNotFoundError("No DHT22 dataset files found in dataset/DHT22_Dataset")
    dht_dfs = []
    for f in dht_files:
        df = pd.read_csv(f)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["temp_c"] = df["temperature_c"].clip(-35.0, 80.0)
        df["hum_pct"] = df["humidity_percent"].clip(0.0, 100.0)
        df["elapsed_s"] = (df["timestamp"] - df["timestamp"].min()).dt.total_seconds()
        dht_dfs.append(df)

    # Load MQ files
    mq_files = sorted(DATASET_DIR.glob("MQ_Dataset/*.csv"))
    if not mq_files:
        raise FileNotFoundError("No MQ dataset files found in dataset/MQ_Dataset")
    mq_dfs = []
    for f in mq_files:
        df = pd.read_csv(f)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["mq2_v"] = df["mq2_ao_voltage"].clip(0.0, 5.0)
        df["mq9_v"] = df["mq9_ao_voltage"].clip(0.0, 5.0)
        df["mq135_v"] = df["mq135_ao_voltage"].clip(0.0, 5.0)
        df["elapsed_s"] = (df["timestamp"] - df["timestamp"].min()).dt.total_seconds()
        mq_dfs.append(df)

    # Load MPM10 files
    mpm_files = sorted(DATASET_DIR.glob("MPM_10_Dataset/*.csv"))
    if not mpm_files:
        raise FileNotFoundError("No MPM10 dataset files found in dataset/MPM_10_Dataset")
    mpm_dfs = []
    for f in mpm_files:
        df = pd.read_csv(f)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        # Handle outliers / invalid PM values safely
        for col in ["pm1_0", "pm2_5", "pm10"]:
            df[col] = df[col].apply(lambda v: v if (isinstance(v, (int, float)) and 0 <= v <= 1000) else np.nan)
            df[col] = df[col].ffill().bfill().fillna(0.0)
        # Enforce physical hierarchy: pm1_0 <= pm2_5 <= pm10
        df["pm1_0"] = np.minimum(df["pm1_0"], df["pm2_5"])
        df["pm2_5"] = np.minimum(df["pm2_5"], df["pm10"])
        df["elapsed_s"] = (df["timestamp"] - df["timestamp"].min()).dt.total_seconds()
        mpm_dfs.append(df)

    logger.info("Found %d DHT22, %d MQ, and %d MPM10 session files.", len(dht_dfs), len(mq_dfs), len(mpm_dfs))

    # Chronologically align streams across sessions using timestamp offset
    aligned_sessions = []
    n_sessions = min(len(dht_dfs), len(mq_dfs), len(mpm_dfs))
    for i in range(n_sessions):
        d = dht_dfs[i].sort_values("elapsed_s")
        q = mq_dfs[i].sort_values("elapsed_s")
        m = mpm_dfs[i].sort_values("elapsed_s")

        merged = pd.merge_asof(
            d[["timestamp", "session", "elapsed_s", "temp_c", "hum_pct"]],
            q[["elapsed_s", "mq2_v", "mq9_v", "mq135_v"]],
            on="elapsed_s",
            tolerance=5.0,
        )
        merged = pd.merge_asof(
            merged,
            m[["elapsed_s", "pm1_0", "pm2_5", "pm10"]],
            on="elapsed_s",
            tolerance=5.0,
        )
        merged = merged.ffill().bfill()
        aligned_sessions.append(merged)

    full_df = pd.concat(aligned_sessions, ignore_index=True)
    logger.info("Successfully aligned dataset: %d clean records.", len(full_df))

    # Build derived features expected by models
    full_df["pm_coarse_ratio"] = np.where(full_df["pm2_5"] > 0.1, (full_df["pm10"] / full_df["pm2_5"]).round(4), 0.0)
    full_df["pm_fine_ratio"] = np.where(full_df["pm1_0"] > 0.1, (full_df["pm2_5"] / full_df["pm1_0"]).round(4), 0.0)
    full_df["mq_mean_v"] = ((full_df["mq2_v"] + full_df["mq9_v"] + full_df["mq135_v"]) / 3.0).round(4)
    full_df["mq_max_v"] = np.maximum(full_df["mq2_v"], np.maximum(full_df["mq9_v"], full_df["mq135_v"])).round(4)
    full_df["mq2_mq9_ratio"] = np.where(full_df["mq9_v"] > 0.01, (full_df["mq2_v"] / full_df["mq9_v"]).round(4), 0.0)
    full_df["mq135_mq2_ratio"] = np.where(full_df["mq2_v"] > 0.01, (full_df["mq135_v"] / full_df["mq2_v"]).round(4), 0.0)

    # Assign environmental pattern label & safety status for supervised/calibrated training
    def assign_pattern(row):
        mq2, mq9, mq135 = row["mq2_v"], row["mq9_v"], row["mq135_v"]
        pm25 = row["pm2_5"]
        if mq9 >= 1.5 and mq9 > mq2 and mq9 > mq135:
            lbl = "CO"
        elif mq2 >= 1.5 or pm25 >= 150:
            lbl = "Smoke"
        elif mq135 >= 1.8:
            lbl = "Alcohol"
        elif mq2 >= 1.2:
            lbl = "LPG"
        else:
            lbl = "CleanAir"

        is_unsafe = (pm25 > 100.0 or mq9 > 1.7 or mq2 > 1.8 or mq135 > 2.0)
        safety = "unsafe" if is_unsafe else "safe"
        return pd.Series([lbl, safety], index=["gas_label", "safety_status"])

    labels = full_df.apply(assign_pattern, axis=1)
    full_df = pd.concat([full_df, labels], axis=1)

    return full_df


# ------------------------------------------------------------------
# Step 2: Backup Previous Artifacts
# ------------------------------------------------------------------
def backup_previous_artifacts() -> Path:
    ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = ARTIFACTS_DIR / "backups" / f"backup_{ts_str}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Backing up previous model artifacts to %s...", backup_dir)

    for fn in [
        "gasnet_weights.npz", "model_metadata.json", "preprocess.pkl",
        "source_classifier_model.pkl", "source_classifier_stats.json", "source_classifier_metadata.json"
    ]:
        for src_dir in [ARTIFACTS_DIR, SERVER_MODELS_DIR, TRAINING_MODELS_DIR]:
            src_file = src_dir / fn
            if src_file.exists() and src_file.is_file():
                shutil.copy2(src_file, backup_dir / f"{src_dir.name}_{fn}")

    logger.info("Backup created successfully.")
    return backup_dir


# ------------------------------------------------------------------
# Step 3: Train / Refresh Pure NumPy TinyGasNet (Anomaly Model)
# ------------------------------------------------------------------
def train_tiny_gasnet(df: pd.DataFrame) -> Tuple[Dict[str, Any], float]:
    logger.info("Step 3: Retraining TinyGasNet Anomaly Detection model (Pure NumPy, PyTorch-Free)...")

    feature_cols = ["mq2_v", "mq9_v", "mq135_v", "temp_c", "hum_pct"]
    X = df[feature_cols].values.astype(np.float32)

    le = LabelEncoder()
    y_class = le.fit_transform(df["gas_label"].values)
    y_safety = (df["safety_status"] == "unsafe").astype(np.float32).values

    # Chronological train (70%) / val (15%) / test (15%) split — prevents leakage
    n = len(df)
    n_train = int(0.70 * n)
    n_val = int(0.15 * n)

    X_train, X_val, X_test = X[:n_train], X[n_train:n_train + n_val], X[n_train + n_val:]
    yc_train, yc_val, yc_test = y_class[:n_train], y_class[n_train:n_train + n_val], y_class[n_train + n_val:]
    ys_train, ys_val, ys_test = y_safety[:n_train], y_safety[n_train:n_train + n_val], y_safety[n_train + n_val:]

    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train).astype(np.float32)
    X_val_s = scaler.transform(X_val).astype(np.float32)
    X_test_s = scaler.transform(X_test).astype(np.float32)

    model = NumPyTinyGasNet(n_features=5, n_classes=len(le.classes_))
    model.fit(X_train_s, yc_train, ys_train, X_val_s, yc_val, ys_val, epochs=50, lr=0.005, batch_size=64)

    # Temperature Scaling for probability calibration (fast vector grid search)
    _, _, val_logits_c, _ = model.forward(X_val_s, train=False)
    best_T = 1.0
    best_nll = float("inf")
    for T_candidate in np.linspace(0.2, 5.0, 97):
        scaled_c = val_logits_c / T_candidate
        exp_c = np.exp(scaled_c - np.max(scaled_c, axis=-1, keepdims=True))
        probs_c = exp_c / np.sum(exp_c, axis=-1, keepdims=True)
        nll = -np.mean(np.log(probs_c[np.arange(len(X_val_s)), yc_val] + 1e-12))
        if nll < best_nll:
            best_nll = nll
            best_T = float(T_candidate)
    optimal_T = float(best_T)

    # Evaluate on test set
    _, _, test_logits_c, test_logit_s = model.forward(X_test_s, train=False)
    scaled_test = test_logits_c / optimal_T
    pred_c = scaled_test.argmax(axis=1)
    prob_s = 1.0 / (1.0 + np.exp(-np.clip(test_logit_s, -15.0, 15.0)))
    pred_s = (prob_s > 0.5).astype(int)

    acc = float(accuracy_score(yc_test, pred_c))
    macro_f1 = float(f1_score(yc_test, pred_c, average="macro", zero_division=0))
    safety_f1 = float(f1_score(ys_test, pred_s, zero_division=0))

    logger.info("TinyGasNet Test Evaluation -> Accuracy: %.4f | Macro-F1: %.4f | Safety-F1: %.4f | T_cal: %.4f",
                acc, macro_f1, safety_f1, optimal_T)

    weights_dict = model.state_dict()
    metadata = {
        "model_version": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "architecture": {
            "n_features": 5,
            "hidden1": 32,
            "hidden2": 16,
            "n_classes": len(le.classes_),
            "p_drop": 0.1,
        },
        "feature_order": ["MQ2_V", "MQ9_V", "MQ135_V", "temperature_C", "humidity_pct"],
        "class_labels": le.classes_.tolist(),
        "calibration_temperature": float(optimal_T),
        "preprocessing": {
            "scaler_mean": scaler.mean_.tolist(),
            "scaler_scale": scaler.scale_.tolist(),
        },
        "evaluation": {
            "accuracy": acc,
            "macro_f1": macro_f1,
            "safety_f1": safety_f1,
            "n_test_samples": len(yc_test),
        },
        "expected_input_ranges": {
            "MQ2_V": [0.0, 5.0],
            "MQ9_V": [0.0, 5.0],
            "MQ135_V": [0.0, 5.0],
            "temperature_C": [-35.0, 80.0],
            "humidity_pct": [0.0, 100.0],
        },
        "export_timestamp": datetime.now().isoformat(),
    }

    artifacts = {
        "weights": weights_dict,
        "metadata": metadata,
        "bundle": {"scaler": scaler, "label_encoder": le, "temperature": optimal_T},
    }
    return artifacts, acc


# ------------------------------------------------------------------
# Step 4: Calibrate Source Classifier Statistics & Decision Tree
# ------------------------------------------------------------------
def calibrate_source_classifier(df: pd.DataFrame) -> Tuple[Dict[str, Any], float]:
    logger.info("Step 4: Calibrating Source Classifier range statistics & Decision Tree...")

    feature_cols = [
        "mq2_v", "mq9_v", "mq135_v", "temp_c", "hum_pct",
        "pm1_0", "pm2_5", "pm10", "pm_coarse_ratio", "pm_fine_ratio",
        "mq_mean_v", "mq_max_v", "mq2_mq9_ratio", "mq135_mq2_ratio"
    ]

    # Map dataset patterns to standard source categories
    source_scenarios = {
        "CLEAN_OR_BACKGROUND": df[df["gas_label"] == "CleanAir"],
        "TRAFFIC": df[(df["gas_label"] == "CO") | ((df["mq9_v"] > 1.2) & (df["pm2_5"] > 30))],
        "HEAVY_DUST": df[(df["pm_coarse_ratio"] > 1.5) & (df["pm10"] > 100)],
        "CONSTRUCTION_ACTIVITY": df[(df["pm10"] > 120) & (df["mq9_v"] > 1.0)],
        "BIOMASS_OR_WASTE_BURNING": df[(df["gas_label"] == "Smoke") & (df["mq2_v"] > 1.5)],
        "INDUSTRIAL_OR_GENERATOR_EMISSIONS": df[(df["mq135_v"] > 1.6) | (df["gas_label"] == "Alcohol")],
        "COOKING_OR_FUEL_COMBUSTION": df[(df["mq2_v"] > 1.2) & (df["pm2_5"] > 40)],
        "INDOOR_ACTIVITY": df[(df["temp_c"] < 32.0) & (df["hum_pct"] > 50) & (df["pm2_5"] < 40)],
    }

    stats: Dict[str, Dict[str, Dict[str, float]]] = {}
    rows = []

    for cat_name, cat_df in source_scenarios.items():
        if len(cat_df) == 0:
            cat_df = df  # Fallback to full dataset if empty
        class_stats = {}
        for feat in feature_cols:
            vals = cat_df[feat].dropna().values
            if len(vals) == 0:
                continue
            med = float(np.median(vals))
            mad = float(np.median(np.abs(vals - med)))
            class_stats[feat] = {
                "median": round(med, 4),
                "mad": round(mad, 4),
                "q25": round(float(np.percentile(vals, 25)), 4),
                "q75": round(float(np.percentile(vals, 75)), 4),
                "min": round(float(np.min(vals)), 4),
                "max": round(float(np.max(vals)), 4),
                "count": int(len(vals)),
            }
        stats[cat_name] = class_stats

        sub = cat_df[feature_cols].copy()
        sub["label"] = cat_name
        rows.append(sub)

    synth_df = pd.concat(rows, ignore_index=True)
    X = synth_df[feature_cols].values.astype(np.float32)
    y = synth_df["label"].values

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=SEED, stratify=y)
    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    dt = DecisionTreeClassifier(
        max_depth=8, min_samples_split=10, min_samples_leaf=5, class_weight="balanced", random_state=SEED
    )
    dt.fit(X_train_s, y_train)

    y_pred = dt.predict(X_test_s)
    acc = float(accuracy_score(y_test, y_pred))
    logger.info("Source Classifier Decision Tree accuracy: %.4f", acc)

    model_bundle = {
        "model": dt,
        "scaler": scaler,
        "class_names": list(dt.classes_),
        "feature_names": feature_cols,
    }

    metadata = {
        "version": f"1.0.0-retrained-{datetime.now().strftime('%Y%m%d')}",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_type": "DecisionTreeClassifier",
        "training_data": f"Calibrated from real dataset ({len(df)} aligned samples)",
        "classes": list(dt.classes_),
        "features": feature_cols,
        "evaluation": {
            "accuracy": acc,
            "tree_depth": int(dt.get_depth()),
            "n_leaves": int(dt.get_n_leaves()),
            "n_train": int(len(X_train)),
            "n_test": int(len(X_test)),
        },
    }

    return {"bundle": model_bundle, "stats": stats, "metadata": metadata}, acc


# ------------------------------------------------------------------
# Step 5: Prime Forecast Model History (48h Retention Policy)
# ------------------------------------------------------------------
def prime_forecast_history(df: pd.DataFrame) -> int:
    logger.info("Step 5: Priming Forecast Model history & verifying 48h retention policy...")

    READINGS_DIR.mkdir(parents=True, exist_ok=True)
    jsonl_path = READINGS_DIR / "readings.jsonl"

    # Convert aligned dataframe to JSONL records
    records = []
    now = datetime.now(timezone.utc)

    for i, row in df.iterrows():
        # Spread timestamps over the last 24 hours to simulate rolling history
        time_offset_s = (len(df) - 1 - i) * 10
        ts = now - pd.Timedelta(seconds=time_offset_s)

        rec = {
            "reading_id": f"rec_{i:05d}",
            "node_id": "uno-q-001",
            "timestamp": ts.isoformat(),
            "environment": {"temperature_C": float(row["temp_c"]), "humidity_pct": float(row["hum_pct"])},
            "particulate_matter": {"PM1_0": float(row["pm1_0"]), "PM2_5": float(row["pm2_5"]), "PM10": float(row["pm10"])},
            "gas_sensors": {
                "MQ2": {"raw_adc": int(row["mq2_v"] * 200), "voltage_V": float(row["mq2_v"])},
                "MQ9": {"raw_adc": int(row["mq9_v"] * 200), "voltage_V": float(row["mq9_v"])},
                "MQ135": {"raw_adc": int(row["mq135_v"] * 200), "voltage_V": float(row["mq135_v"])},
            },
        }
        records.append(rec)

    # Filter according to 48h retention policy
    cutoff = now - pd.Timedelta(hours=48)
    valid_records = [r for r in records if pd.to_datetime(r["timestamp"]) >= cutoff]

    with open(jsonl_path, "w") as f:
        for r in valid_records:
            f.write(json.dumps(r) + "\n")

    logger.info("Ingested %d valid records into %s (48h policy verified).", len(valid_records), jsonl_path)
    return len(valid_records)


# ------------------------------------------------------------------
# Step 6: Save & Deploy Artifacts to All Expected Paths
# ------------------------------------------------------------------
def save_and_deploy_artifacts(gasnet_artifacts: Dict[str, Any], sc_artifacts: Dict[str, Any]) -> None:
    logger.info("Step 6: Saving & deploying new model artifacts...")

    for d in [ARTIFACTS_DIR, SERVER_MODELS_DIR, TRAINING_MODELS_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    # Save NumPy weights npz
    npz_data = gasnet_artifacts["weights"]
    np.savez_compressed(TRAINING_MODELS_DIR / "gasnet_weights.npz", **npz_data)
    np.savez_compressed(SERVER_MODELS_DIR / "gasnet_weights.npz", **npz_data)
    np.savez_compressed(ARTIFACTS_DIR / "gasnet_weights.npz", **npz_data)

    # Save TinyGasNet Metadata
    meta_json = json.dumps(gasnet_artifacts["metadata"], indent=2)
    with open(TRAINING_MODELS_DIR / "model_metadata.json", "w") as f:
        f.write(meta_json)
    with open(SERVER_MODELS_DIR / "model_metadata.json", "w") as f:
        f.write(meta_json)
    with open(ARTIFACTS_DIR / "model_metadata.json", "w") as f:
        f.write(meta_json)

    # Save Preprocessing bundle
    joblib.dump(gasnet_artifacts["bundle"], TRAINING_MODELS_DIR / "preprocess.pkl")
    joblib.dump(gasnet_artifacts["bundle"], ARTIFACTS_DIR / "preprocess.pkl")

    # Save Source Classifier artifacts
    joblib.dump(sc_artifacts["bundle"], ARTIFACTS_DIR / "source_classifier_model.pkl")
    with open(ARTIFACTS_DIR / "source_classifier_stats.json", "w") as f:
        json.dump(sc_artifacts["stats"], f, indent=2)
    with open(ARTIFACTS_DIR / "source_classifier_metadata.json", "w") as f:
        json.dump(sc_artifacts["metadata"], f, indent=2)

    logger.info("All new model artifacts saved and deployed across:")
    logger.info("  - %s", ARTIFACTS_DIR)
    logger.info("  - %s", SERVER_MODELS_DIR)
    logger.info("  - %s", TRAINING_MODELS_DIR)


# ------------------------------------------------------------------
# Step 7: Verify Inference Code Automatically Loads New Artifacts
# ------------------------------------------------------------------
def verify_inference_loading() -> bool:
    logger.info("Step 7: Verifying automatic artifact loading in existing inference adapters...")

    # Add server path to sys.path
    server_path = str(PROJECT_ROOT / "Intelligence" / "Server")
    if server_path not in sys.path:
        sys.path.insert(0, server_path)

    # 1. Test NumpyGasNetAdapter
    try:
        from app.services.numpy_inference import NumpyGasNetAdapter
        adapter = NumpyGasNetAdapter(artifacts_dir=ARTIFACTS_DIR)
        adapter.load()
        assert adapter._loaded, "NumpyGasNetAdapter failed to load newly trained weights!"
        logger.info("  [PASS] NumpyGasNetAdapter successfully loaded retrained artifacts.")
    except Exception as e:
        logger.error("  [FAIL] NumpyGasNetAdapter verification error: %s", e)
        return False

    # 2. Test SourceClassifier
    try:
        from app.source_classifier.classifier import SourceClassifier
        sc = SourceClassifier(artifacts_dir=ARTIFACTS_DIR)
        sc_loaded = sc.load()
        assert sc_loaded, "SourceClassifier failed to load newly calibrated artifacts!"
        logger.info("  [PASS] SourceClassifier successfully loaded retrained artifacts.")
    except Exception as e:
        logger.error("  [FAIL] SourceClassifier verification error: %s", e)
        return False

    return True


# ------------------------------------------------------------------
# Main Retraining Pipeline Execution
# ------------------------------------------------------------------
def main() -> None:
    logger.info("=" * 70)
    logger.info("NavosEdge Phase 12 — PyTorch-Free Retraining & Model Update Pipeline")
    logger.info("=" * 70)

    t0 = time.time()

    # Step 1: Load & align
    df = load_and_validate_dataset()

    # Step 2: Backup previous artifacts
    backup_dir = backup_previous_artifacts()

    # Step 3: Train TinyGasNet
    gasnet_artifacts, gasnet_acc = train_tiny_gasnet(df)

    # Step 4: Calibrate Source Classifier
    sc_artifacts, sc_acc = calibrate_source_classifier(df)

    # Step 5: Prime Forecast History
    records_count = prime_forecast_history(df)

    # Step 6: Deploy Artifacts
    save_and_deploy_artifacts(gasnet_artifacts, sc_artifacts)

    # Step 7: Verify Inference Code
    success = verify_inference_loading()

    elapsed = time.time() - t0

    logger.info("=" * 70)
    logger.info("Pipeline Complete!")
    logger.info("  Elapsed time: %.2f seconds", elapsed)
    logger.info("  Dataset size: %d aligned records", len(df))
    logger.info("  TinyGasNet Test Accuracy: %.4f", gasnet_acc)
    logger.info("  Source Classifier Accuracy: %.4f", sc_acc)
    logger.info("  Forecast History Primed: %d records", records_count)
    logger.info("  Backup saved at: %s", backup_dir)
    logger.info("  Inference Verification: %s", "PASSED" if success else "FAILED")
    logger.info("=" * 70)

    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
