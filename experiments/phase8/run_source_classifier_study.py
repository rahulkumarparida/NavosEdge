"""
NavosEdge Phase 8 (Part A) — SourceClassifier Generalization, Class Overlap,
Candidate Model Comparison, Calibration, and OOD Abstention Study.

Preserves all original artifacts in Intelligence/Server/artifacts/ untouched.
Uses strict seed-separated Train (seed=42) / Val (seed=101) / Test (seed=777)
and cross-generator evaluation (ScenarioGenerator seed=999).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import pickle
import sys
import time
from typing import Any, Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import (
    ExtraTreesClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.metrics import (
    accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVER_ROOT = REPO_ROOT / "Intelligence" / "Server"
for p in (str(SERVER_ROOT), str(REPO_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from Simulator.generator import ScenarioGenerator
from app.schemas.sensor import SensorPayload
from app.source_classifier.categories import ALL_SOURCE_CLASSIFIER_FEATURES
from app.source_classifier.classifier import SourceClassifier
from app.source_classifier.features import extract_source_features, features_to_model_array

SEED = 42
OUT_DIR = Path(__file__).resolve().parent / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_audit_suite(seed: int, include_ambiguous: bool = False) -> Tuple[np.ndarray, np.ndarray, List[Dict[str, Any]]]:
    path = REPO_ROOT / "test_data" / "phase2_model_audit" / f"synthetic_source_classifier_eval_seed_{seed}.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    X_rows: List[List[float]] = []
    y_rows: List[str] = []
    meta_rows: List[Dict[str, Any]] = []
    for item in raw["data"]:
        is_amb = bool(item.get("is_mixed_or_ambiguous", False))
        if not include_ambiguous and is_amb:
            continue
        payload = SensorPayload(**item["payload"])
        feats, _ = extract_source_features(payload)
        arr = features_to_model_array(feats, ALL_SOURCE_CLASSIFIER_FEATURES, fill_value=0.0)
        X_rows.append(arr)
        y_rows.append(str(item["expected_source"]))
        meta_rows.append(item)
    return np.array(X_rows, dtype=np.float32), np.array(y_rows), meta_rows


def load_scenario_generator_suite(seed: int = 42, n_per_class: int = 30) -> Tuple[np.ndarray, np.ndarray]:
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
    X_rows: List[List[float]] = []
    y_rows: List[str] = []
    for scen, expected in scenario_to_expected.items():
        gen = ScenarioGenerator(node_id=f"p8-{scen}", scenario=scen, seed=seed)
        for _ in range(n_per_class):
            payload = SensorPayload(**gen.next_payload(10.0))
            feats, _ = extract_source_features(payload)
            arr = features_to_model_array(feats, ALL_SOURCE_CLASSIFIER_FEATURES, fill_value=0.0)
            X_rows.append(arr)
            y_rows.append(expected)
    return np.array(X_rows, dtype=np.float32), np.array(y_rows)


def bootstrap_ci(y_true: np.ndarray, y_pred: np.ndarray, labels: List[str], n_boot: int = 300) -> Dict[str, List[float]]:
    rng = np.random.default_rng(SEED)
    n = len(y_true)
    accs, f1s = [], []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        yt, yp = y_true[idx], y_pred[idx]
        accs.append(accuracy_score(yt, yp))
        f1s.append(f1_score(yt, yp, labels=labels, average="macro", zero_division=0))
    return {
        "accuracy_95ci": [round(float(np.percentile(accs, 2.5)), 4), round(float(np.percentile(accs, 97.5)), 4)],
        "macro_f1_95ci": [round(float(np.percentile(f1s, 2.5)), 4), round(float(np.percentile(f1s, 97.5)), 4)],
    }


def compute_ece(probs: np.ndarray, y_true_idx: np.ndarray, n_bins: int = 10) -> float:
    conf = np.max(probs, axis=1)
    pred = np.argmax(probs, axis=1)
    acc = (pred == y_true_idx).astype(float)
    ece = 0.0
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    for b0, b1 in zip(bins[:-1], bins[1:]):
        mask = (conf > b0) & (conf <= b1) if b0 > 0 else (conf >= b0) & (conf <= b1)
        if np.any(mask):
            ece += (np.sum(mask) / len(conf)) * abs(np.mean(acc[mask]) - np.mean(conf[mask]))
    return round(float(ece), 4)


def main() -> None:
    artifacts_dir = SERVER_ROOT / "artifacts"
    orig_pkl = artifacts_dir / "source_classifier_model.pkl"
    orig_sha = hashlib.sha256(orig_pkl.read_bytes()).hexdigest()

    # 1. A1: Reproduce Phase 7 baseline on ScenarioGenerator(seed=42)
    clf = SourceClassifier(artifacts_dir=artifacts_dir)
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
    y_true_p7, y_pred_p7 = [], []
    for scen, expected in scenario_to_expected.items():
        gen = ScenarioGenerator(node_id=f"eval-{scen}", scenario=scen, seed=SEED)
        for _ in range(30):
            res = clf.classify(SensorPayload(**gen.next_payload(10.0)))
            y_true_p7.append(expected)
            y_pred_p7.append(res.get("top_source") or "ABSTAIN")

    labels_8 = sorted(list(scenario_to_expected.values()))
    p7_acc = accuracy_score(y_true_p7, y_pred_p7)
    p7_f1 = f1_score(y_true_p7, y_pred_p7, labels=labels_8, average="macro", zero_division=0)

    # 2. A2: Investigate Class Overlap (Training stats vs ScenarioGenerator)
    stats_json = json.loads((artifacts_dir / "source_classifier_stats.json").read_text(encoding="utf-8"))
    X_sg, y_sg = load_scenario_generator_suite(seed=SEED, n_per_class=30)
    df_sg = pd.DataFrame(X_sg, columns=ALL_SOURCE_CLASSIFIER_FEATURES)
    df_sg["label"] = y_sg

    confused_pairs = [
        ("HEAVY_DUST", "CONSTRUCTION_ACTIVITY"),
        ("COOKING_OR_FUEL_COMBUSTION", "BIOMASS_OR_WASTE_BURNING"),
        ("TRAFFIC", "INDUSTRIAL_OR_GENERATOR_EMISSIONS"),
    ]
    overlap_analysis: Dict[str, Any] = {}
    for c1, c2 in confused_pairs:
        d1 = df_sg[df_sg["label"] == c1]
        d2 = df_sg[df_sg["label"] == c2]
        feat_diffs = {}
        for feat in ALL_SOURCE_CLASSIFIER_FEATURES:
            m1, s1 = float(d1[feat].mean()), float(d1[feat].std())
            m2, s2 = float(d2[feat].mean()), float(d2[feat].std())
            pooled = np.sqrt(((s1 ** 2) + (s2 ** 2)) / 2.0) + 1e-9
            cohen_d = abs(m1 - m2) / pooled
            train_med1 = stats_json.get(c1, {}).get(feat, {}).get("median")
            train_med2 = stats_json.get(c2, {}).get(feat, {}).get("median")
            feat_diffs[feat] = {
                "sg_mean_a": round(m1, 3),
                "sg_mean_b": round(m2, 3),
                "cohen_d_sg": round(float(cohen_d), 3),
                "train_med_a": train_med1,
                "train_med_b": train_med2,
            }
        # Top 4 most overlapping (smallest Cohen's d) and top 4 most separating features
        sorted_feats = sorted(feat_diffs.items(), key=lambda kv: kv[1]["cohen_d_sg"])
        overlap_analysis[f"{c1}_vs_{c2}"] = {
            "most_overlapping_features": dict(sorted_feats[:4]),
            "most_separating_features": dict(sorted_feats[-4:]),
        }

    # 3. A3: Strict Train (seed=42) / Val (seed=101) / Test (seed=777) + Cross-Generator (ScenarioGenerator seed=999)
    X_train, y_train, _ = load_audit_suite(42, include_ambiguous=False)
    X_val, y_val, _ = load_audit_suite(101, include_ambiguous=False)
    X_test, y_test, _ = load_audit_suite(777, include_ambiguous=False)
    X_amb, y_amb, _ = load_audit_suite(777, include_ambiguous=True)
    X_sg_unseen, y_sg_unseen = load_scenario_generator_suite(seed=999, n_per_class=40)

    le = LabelEncoder()
    le.fit(labels_8)
    y_tr_i = le.transform(y_train)
    y_va_i = le.transform(y_val)
    y_te_i = le.transform(y_test)
    y_sg_i = le.transform(y_sg_unseen)

    scaler = StandardScaler()
    X_tr_s = scaler.fit_transform(X_train)
    X_va_s = scaler.transform(X_val)
    X_te_s = scaler.transform(X_test)
    X_sg_s = scaler.transform(X_sg_unseen)

    # Also evaluate original bundle directly on seed=777
    orig_bundle = joblib.load(orig_pkl)
    orig_model = orig_bundle["model"]
    orig_scaler = orig_bundle["scaler"]

    def eval_orig_on(X_raw: np.ndarray, y_true_str: np.ndarray) -> Dict[str, Any]:
        Xs = orig_scaler.transform(X_raw)
        t0 = time.perf_counter()
        yp = orig_model.predict(Xs)
        lat_ms = ((time.perf_counter() - t0) * 1000.0) / len(X_raw)
        probs = orig_model.predict_proba(Xs)
        yi = le.transform(y_true_str)
        return {
            "accuracy": round(float(accuracy_score(y_true_str, yp)), 4),
            "macro_f1": round(float(f1_score(y_true_str, yp, labels=labels_8, average="macro", zero_division=0)), 4),
            "ece": compute_ece(probs, yi),
            "infer_ms_per_sample": round(lat_ms, 4),
            "ci_95": bootstrap_ci(y_true_str, yp, labels_8),
        }

    candidates = {
        "DecisionTree_d8": DecisionTreeClassifier(max_depth=8, min_samples_split=10, min_samples_leaf=5, class_weight="balanced", random_state=SEED),
        "RandomForest_100": RandomForestClassifier(n_estimators=100, max_depth=10, min_samples_leaf=3, class_weight="balanced", random_state=SEED),
        "ExtraTrees_100": ExtraTreesClassifier(n_estimators=100, max_depth=12, min_samples_leaf=3, class_weight="balanced", random_state=SEED),
        "HistGradientBoosting": HistGradientBoostingClassifier(max_depth=6, learning_rate=0.08, max_iter=120, random_state=SEED),
        "SVC_RBF_Calibrated": CalibratedClassifierCV(SVC(C=2.0, kernel="rbf", class_weight="balanced", random_state=SEED), cv=3),
    }

    model_results: Dict[str, Any] = {
        "Original_Artifact_DT": {
            "model_sha256": orig_sha,
            "size_kb": round(orig_pkl.stat().st_size / 1024, 2),
            "test_seed777": eval_orig_on(X_test, y_test),
            "cross_gen_sg999": eval_orig_on(X_sg_unseen, y_sg_unseen),
        }
    }

    best_rf_bundle = None
    for name, model in candidates.items():
        t_fit = time.perf_counter()
        model.fit(X_tr_s, y_tr_i)
        train_ms = (time.perf_counter() - t_fit) * 1000.0

        def eval_split(Xs: np.ndarray, yi: np.ndarray, y_str: np.ndarray) -> Dict[str, Any]:
            t0 = time.perf_counter()
            yp_i = model.predict(Xs)
            lat_ms = ((time.perf_counter() - t0) * 1000.0) / len(Xs)
            probs = model.predict_proba(Xs)
            yp_str = le.inverse_transform(yp_i)
            _, r, f1, _ = precision_recall_fscore_support(y_str, yp_str, labels=labels_8, zero_division=0)
            return {
                "accuracy": round(float(accuracy_score(y_str, yp_str)), 4),
                "macro_f1": round(float(f1_score(y_str, yp_str, labels=labels_8, average="macro", zero_division=0)), 4),
                "ece": compute_ece(probs, yi),
                "infer_ms_per_sample": round(lat_ms, 4),
                "ci_95": bootstrap_ci(y_str, yp_str, labels_8),
                "per_class_recall": {labels_8[i]: round(float(r[i]), 4) for i in range(len(labels_8))},
                "confusion_matrix": confusion_matrix(y_str, yp_str, labels=labels_8).tolist(),
            }

        size_kb = round(len(pickle.dumps({"model": model, "scaler": scaler})) / 1024, 2)
        res_entry = {
            "train_time_ms": round(train_ms, 2),
            "size_kb": size_kb,
            "val_seed101": eval_split(X_va_s, y_va_i, y_val),
            "test_seed777": eval_split(X_te_s, y_te_i, y_test),
            "cross_gen_sg999": eval_split(X_sg_s, y_sg_i, y_sg_unseen),
        }
        model_results[name] = res_entry
        if name == "RandomForest_100":
            best_rf_bundle = (model, probs_te := model.predict_proba(X_te_s))

    # 4. A4: OOD / Abstention Threshold Sweep on Test (seed=777) & Ambiguous samples
    abstention_curve = []
    if best_rf_bundle is not None:
        rf_model, probs_te = best_rf_bundle
        max_p = np.max(probs_te, axis=1)
        pred_te = le.inverse_transform(np.argmax(probs_te, axis=1))
        for tau in (0.30, 0.40, 0.50, 0.60, 0.70, 0.80):
            keep = max_p >= tau
            cov = float(np.mean(keep))
            sel_acc = float(accuracy_score(y_test[keep], pred_te[keep])) if np.any(keep) else 0.0
            abstention_curve.append({"threshold": tau, "coverage": round(cov, 4), "selective_accuracy": round(sel_acc, 4)})

    out = {
        "phase7_baseline_reproduction": {
            "original_artifact_sha256": orig_sha,
            "n_samples": len(y_true_p7),
            "accuracy": round(float(p7_acc), 4),
            "macro_f1": round(float(p7_f1), 4),
            "reproduced_exact": abs(p7_acc - 0.4792) < 1e-4 and abs(p7_f1 - 0.4043) < 1e-4,
        },
        "class_overlap_analysis": overlap_analysis,
        "dataset_splits": {
            "train_seed_42_non_ambiguous": len(X_train),
            "val_seed_101_non_ambiguous": len(X_val),
            "test_seed_777_non_ambiguous": len(X_test),
            "cross_gen_sg_seed_999": len(X_sg_unseen),
            "features": ALL_SOURCE_CLASSIFIER_FEATURES,
            "labels": labels_8,
        },
        "candidate_comparison": model_results,
        "abstention_curve_rf_seed777": abstention_curve,
    }
    out_file = OUT_DIR / "phase8_source_classifier_study.json"
    out_file.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("Saved SourceClassifier study to", out_file)
    print("Baseline reproduced:", out["phase7_baseline_reproduction"])
    for mname, mres in model_results.items():
        print(
            f"  {mname:22s} | seed777 acc={mres['test_seed777']['accuracy']:.4f} f1={mres['test_seed777']['macro_f1']:.4f} ece={mres['test_seed777']['ece']:.4f} | "
            f"sg999 acc={mres['cross_gen_sg999']['accuracy']:.4f} f1={mres['cross_gen_sg999']['macro_f1']:.4f}"
        )


if __name__ == "__main__":
    main()

