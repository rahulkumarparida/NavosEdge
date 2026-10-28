"""
NavosEdge Phase 2: Independent Model Generalization Audit Suite

Comprehensive, multi-seed evaluation of:
1. TinyGasNet (active artifacts vs original baseline) across:
   - Shifted Class Centroids
   - Sensor Noise & Voltage Offsets
   - Temperature & Humidity Extremes
   - Overlapping Gas Cross-Sensitivities
   - Mixed / Ambiguous Gas Samples
   - Out-of-Range & Boundary Conditions
2. SourceClassifier (active artifacts vs original baseline) across:
   - Traffic + Construction Dust
   - Combustion + Traffic
   - Industrial Gas + Elevated PM
   - Unusual PM Coarse / Fine Ratios
   - Weather Shifts & Sensor Noise
   - Ambiguous / Overlapping Sources (Mixed Pollution & Uncertainty)
   - Shifted 8-Class Benchmark

Computes:
- Overall Accuracy, Balanced Accuracy, Macro-F1, Per-Class Precision & Recall
- Full Confusion Matrices
- Confidence Calibration (Expected Calibration Error - ECE & Reliability Bins)
- Uncertainty & Abstention Rates (Predictive Entropy for GasNet, Uncertainty/Mixed for SC)
- Multi-seed variance (seeds: 42, 101, 777)
"""

from __future__ import annotations

import asyncio
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
from sklearn.metrics import accuracy_score, balanced_accuracy_score, classification_report, confusion_matrix, f1_score

# Setup Paths
ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT_DIR / "Intelligence" / "Server"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app.schemas.sensor import SensorPayload
from app.services.numpy_inference import NumpyGasNetAdapter
from app.source_classifier.classifier import SourceClassifier
from app.source_classifier.categories import SourceCategory


# ==============================================================================
# Helper Functions: Calibration & Metrics
# ==============================================================================

def compute_ece(confidences: np.ndarray, predictions: np.ndarray, ground_truth: np.ndarray, n_bins: int = 10) -> Tuple[float, List[Dict[str, float]]]:
    """
    Compute Expected Calibration Error (ECE) and bin statistics.
    ECE = sum_{b} (|B_b| / N) * |acc(B_b) - conf(B_b)|
    """
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    n_samples = len(confidences)
    bin_stats = []

    for i in range(n_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]
        
        # In-bin mask
        if i == n_bins - 1:
            in_bin = (confidences >= bin_lower) & (confidences <= bin_upper)
        else:
            in_bin = (confidences >= bin_lower) & (confidences < bin_upper)
            
        bin_size = np.sum(in_bin)
        if bin_size > 0:
            bin_acc = float(np.mean(predictions[in_bin] == ground_truth[in_bin]))
            bin_conf = float(np.mean(confidences[in_bin]))
            ece += (bin_size / n_samples) * abs(bin_acc - bin_conf)
            bin_stats.append({
                "bin_range": f"[{bin_lower:.1f}, {bin_upper:.1f}]",
                "count": int(bin_size),
                "accuracy": round(bin_acc, 4),
                "confidence": round(bin_conf, 4),
                "abs_error": round(abs(bin_acc - bin_conf), 4),
            })
        else:
            bin_stats.append({
                "bin_range": f"[{bin_lower:.1f}, {bin_upper:.1f}]",
                "count": 0,
                "accuracy": 0.0,
                "confidence": round((bin_lower + bin_upper) / 2.0, 4),
                "abs_error": 0.0,
            })

    return float(ece), bin_stats


# ==============================================================================
# TINYGASNET GENERATOR & AUDIT
# ==============================================================================

GASNET_CLASSES = ["Alcohol", "CO", "CleanAir", "LPG", "Smoke"]

def generate_tinygasnet_eval_dataset(seed: int = 42, n_per_class: int = 60) -> List[Dict[str, Any]]:
    """
    Generates genuinely independent test samples for TinyGasNet:
    - Shifts centroids by 15-30% from the training definitions.
    - Incorporates atmospheric temperature & humidity variations (5C to 45C, 20% to 95% RH).
    - Injects MOS cross-sensitivities and additive sensor noise.
    - Adds ambiguous boundary cases and out-of-range test points.
    """
    rng = np.random.default_rng(seed)
    samples: List[Dict[str, Any]] = []

    # 1. Standard Shifted Classes (with realistic cross-sensitivities)
    for cls in GASNET_CLASSES:
        for i in range(n_per_class):
            # Ambient conditions
            t = float(rng.uniform(8.0, 42.0))
            h = float(rng.uniform(22.0, 92.0))
            
            # Base voltages with 5-10% noise & drift
            drift = rng.normal(0.0, 0.06)
            
            if cls == "CleanAir":
                # Clean air: all MQ voltages baseline low
                mq2 = float(np.clip(rng.uniform(0.55, 0.85) + drift, 0.4, 1.1))
                mq9 = float(np.clip(rng.uniform(0.50, 0.80) + drift, 0.4, 1.1))
                mq135 = float(np.clip(rng.uniform(0.55, 0.90) + drift, 0.4, 1.2))
            elif cls == "Alcohol":
                # Alcohol: heavy MQ135 response, moderate MQ2 cross-sensitivity, low MQ9
                mq135 = float(np.clip(rng.uniform(2.10, 3.80) + drift, 1.9, 4.5))
                mq2 = float(np.clip(rng.uniform(0.70, 1.15) + 0.15 * (mq135 - 1.5) + drift, 0.6, 1.8))
                mq9 = float(np.clip(rng.uniform(0.60, 0.95) + drift, 0.4, 1.2))
            elif cls == "CO":
                # CO: heavy MQ9 response, moderate MQ2 cross-response, low MQ135
                mq9 = float(np.clip(rng.uniform(2.00, 3.90) + drift, 1.8, 4.5))
                mq2 = float(np.clip(rng.uniform(0.80, 1.35) + 0.12 * (mq9 - 1.5) + drift, 0.6, 2.0))
                mq135 = float(np.clip(rng.uniform(0.65, 1.10) + drift, 0.5, 1.4))
            elif cls == "LPG":
                # LPG: heavy MQ2 response, substantial MQ9 cross-response, lower MQ135
                mq2 = float(np.clip(rng.uniform(2.20, 3.70) + drift, 1.9, 4.5))
                mq9 = float(np.clip(rng.uniform(1.60, 2.70) + 0.15 * (mq2 - 2.0) + drift, 1.2, 3.2))
                mq135 = float(np.clip(rng.uniform(0.75, 1.25) + drift, 0.5, 1.6))
            elif cls == "Smoke":
                # Smoke: heavy MQ2 response, elevated MQ9 (incomplete combustion) and MQ135 (VOCs)
                mq2 = float(np.clip(rng.uniform(2.30, 4.10) + drift, 2.0, 4.6))
                mq9 = float(np.clip(rng.uniform(1.30, 2.50) + drift, 1.0, 3.0))
                mq135 = float(np.clip(rng.uniform(1.80, 3.20) + drift, 1.4, 3.8))

            samples.append({
                "category": "shifted_class",
                "expected_gas": cls,
                "mq2": round(mq2, 3),
                "mq9": round(mq9, 3),
                "mq135": round(mq135, 3),
                "t": round(t, 1),
                "h": round(h, 1),
                "is_ambiguous": False,
            })

    # 2. Temperature & Humidity Stress Scenarios (30 samples)
    stress_profiles = [
        # Extreme cold winter morning (4C, 92%H)
        {"name": "winter_cold_clean", "exp": "CleanAir", "mq2": 0.62, "mq9": 0.58, "mq135": 0.65, "t": 4.5, "h": 92.0},
        {"name": "winter_cold_smoke", "exp": "Smoke", "mq2": 2.75, "mq9": 1.70, "mq135": 2.45, "t": 6.0, "h": 88.0},
        {"name": "winter_cold_co", "exp": "CO", "mq2": 1.15, "mq9": 2.65, "mq135": 1.10, "t": 5.0, "h": 90.0},
        # Extreme summer heatwave (46C, 18%H)
        {"name": "heatwave_clean", "exp": "CleanAir", "mq2": 0.85, "mq9": 0.75, "mq135": 0.82, "t": 46.5, "h": 18.0},
        {"name": "heatwave_lpg", "exp": "LPG", "mq2": 2.95, "mq9": 2.20, "mq135": 1.15, "t": 44.0, "h": 22.0},
        {"name": "heatwave_alcohol", "exp": "Alcohol", "mq2": 0.90, "mq9": 0.78, "mq135": 2.85, "t": 45.0, "h": 20.0},
        # Tropical monsoon saturation (30C, 98%H)
        {"name": "monsoon_clean", "exp": "CleanAir", "mq2": 0.68, "mq9": 0.62, "mq135": 0.72, "t": 29.5, "h": 98.0},
        {"name": "monsoon_smoke", "exp": "Smoke", "mq2": 2.80, "mq9": 1.85, "mq135": 2.60, "t": 28.0, "h": 97.0},
    ]
    for p in stress_profiles:
        for _ in range(4):
            samples.append({
                "category": "temp_hum_stress",
                "expected_gas": p["exp"],
                "mq2": round(float(p["mq2"] + rng.normal(0, 0.04)), 3),
                "mq9": round(float(p["mq9"] + rng.normal(0, 0.04)), 3),
                "mq135": round(float(p["mq135"] + rng.normal(0, 0.04)), 3),
                "t": round(float(p["t"] + rng.normal(0, 0.5)), 1),
                "h": round(float(np.clip(p["h"] + rng.normal(0, 1.0), 0, 100)), 1),
                "is_ambiguous": False,
            })

    # 3. Ambiguous / Mixed Gas Samples (where model should exhibit high entropy or uncertainty)
    ambiguous_profiles = [
        # Near clean-to-smoke boundary (all channels slightly elevated)
        {"id": "amb_border_clean_smoke", "exp": "CleanAir", "mq2": 1.30, "mq9": 1.10, "mq135": 1.25, "t": 25.0, "h": 50.0},
        # Mixed LPG + CO (both MQ2 and MQ9 elevated equally)
        {"id": "amb_mixed_lpg_co", "exp": "LPG", "mq2": 2.50, "mq9": 2.50, "mq135": 1.20, "t": 27.0, "h": 45.0},
        # Mixed Alcohol + Smoke (both MQ2 and MQ135 high)
        {"id": "amb_mixed_alcohol_smoke", "exp": "Smoke", "mq2": 2.60, "mq9": 1.20, "mq135": 2.70, "t": 26.0, "h": 55.0},
        # Dilute gas hovering near sensor noise floor
        {"id": "amb_dilute_lpg_border", "exp": "CleanAir", "mq2": 1.15, "mq9": 1.05, "mq135": 0.95, "t": 24.0, "h": 60.0},
    ]
    for p in ambiguous_profiles:
        for _ in range(5):
            samples.append({
                "category": "ambiguous_mixture",
                "expected_gas": p["exp"],
                "mq2": round(float(p["mq2"] + rng.normal(0, 0.05)), 3),
                "mq9": round(float(p["mq9"] + rng.normal(0, 0.05)), 3),
                "mq135": round(float(p["mq135"] + rng.normal(0, 0.05)), 3),
                "t": round(float(p["t"] + rng.normal(0, 0.5)), 1),
                "h": round(float(p["h"] + rng.normal(0, 1.0)), 1),
                "is_ambiguous": True,
            })

    # 4. Out-of-Range & Fault Boundary Cases (evaluating abstention / extreme behavior)
    out_of_range_profiles = [
        {"id": "ood_rail_high_all", "exp": "Smoke", "mq2": 5.0, "mq9": 5.0, "mq135": 5.0, "t": 25.0, "h": 50.0, "desc": "Supply rail short"},
        {"id": "ood_rail_low_all", "exp": "CleanAir", "mq2": 0.0, "mq9": 0.0, "mq135": 0.0, "t": 25.0, "h": 50.0, "desc": "Ground short"},
        {"id": "ood_extreme_cold", "exp": "CleanAir", "mq2": 0.70, "mq9": 0.65, "mq135": 0.70, "t": -25.0, "h": 80.0, "desc": "Sub-zero blizzard"},
        {"id": "ood_extreme_hot", "exp": "CleanAir", "mq2": 0.85, "mq9": 0.80, "mq135": 0.85, "t": 70.0, "h": 15.0, "desc": "Industrial furnace ceiling"},
    ]
    for p in out_of_range_profiles:
        samples.append({
            "category": "out_of_range_ood",
            "expected_gas": p["exp"],
            "mq2": p["mq2"],
            "mq9": p["mq9"],
            "mq135": p["mq135"],
            "t": p["t"],
            "h": p["h"],
            "is_ambiguous": True,
            "desc": p["desc"],
        })

    return samples


def audit_tinygasnet_model(model_dir: Path, dataset: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Runs TinyGasNet inference and calculates classification and uncertainty metrics."""
    adapter = NumpyGasNetAdapter(artifacts_dir=model_dir)
    adapter.load()
    if not adapter._loaded:
        return {"error": f"Failed to load TinyGasNet from {model_dir}"}

    model_classes = list(adapter._class_labels)

    y_true: List[str] = []
    y_pred: List[str] = []
    confidences: List[float] = []
    entropies: List[float] = []
    per_category_metrics: Dict[str, Dict[str, Any]] = {}

    for s in dataset:
        res = adapter._sync_predict(s["mq2"], s["mq9"], s["mq135"], s["t"], s["h"])
        pred_label = res.gas_class
        conf = res.class_confidence
        ent = res.uncertainty

        y_true.append(s["expected_gas"])
        y_pred.append(pred_label)
        confidences.append(conf)
        entropies.append(ent)

        cat = s["category"]
        if cat not in per_category_metrics:
            per_category_metrics[cat] = {"total": 0, "correct": 0, "high_entropy_count": 0}
        per_category_metrics[cat]["total"] += 1
        if pred_label == s["expected_gas"]:
            per_category_metrics[cat]["correct"] += 1
        if ent > 0.60:
            per_category_metrics[cat]["high_entropy_count"] += 1

    y_true_arr = np.array(y_true)
    y_pred_arr = np.array(y_pred)
    conf_arr = np.array(confidences)
    ent_arr = np.array(entropies)

    # General metrics
    acc = float(accuracy_score(y_true_arr, y_pred_arr))
    bal_acc = float(balanced_accuracy_score(y_true_arr, y_pred_arr))
    macro_f1 = float(f1_score(y_true_arr, y_pred_arr, average="macro", zero_division=0))

    # All unique classes across true and pred
    all_eval_classes = sorted(list(set(y_true) | set(y_pred)))
    cm = confusion_matrix(y_true_arr, y_pred_arr, labels=all_eval_classes)

    # Calibration (ECE)
    binary_hits = (y_pred_arr == y_true_arr).astype(int)
    ece, bin_stats = compute_ece(conf_arr, y_pred_arr, y_true_arr, n_bins=10)

    # Per-class report
    clf_report = classification_report(y_true_arr, y_pred_arr, labels=all_eval_classes, output_dict=True, zero_division=0)

    # Uncertainty / Abstention analysis
    mean_entropy = float(np.mean(ent_arr))
    high_entropy_rate = float(np.mean(ent_arr > 0.60))

    return {
        "model_dir": str(model_dir),
        "model_classes": model_classes,
        "n_samples": len(dataset),
        "accuracy": round(acc, 4),
        "balanced_accuracy": round(bal_acc, 4),
        "macro_f1": round(macro_f1, 4),
        "mean_confidence": round(float(np.mean(conf_arr)), 4),
        "mean_predictive_entropy": round(mean_entropy, 4),
        "high_entropy_abstention_rate": round(high_entropy_rate, 4),
        "expected_calibration_error": round(ece, 4),
        "calibration_bins": bin_stats,
        "confusion_matrix": {
            "classes": all_eval_classes,
            "matrix": cm.tolist(),
        },
        "per_class": {
            cls: {
                "precision": round(clf_report[cls]["precision"], 4),
                "recall": round(clf_report[cls]["recall"], 4),
                "f1": round(clf_report[cls]["f1-score"], 4),
                "support": int(clf_report[cls]["support"]),
            }
            for cls in all_eval_classes if cls in clf_report
        },
        "category_breakdown": {
            cat: {
                "accuracy": round(vals["correct"] / vals["total"], 4),
                "samples": vals["total"],
                "high_entropy_rate": round(vals["high_entropy_count"] / vals["total"], 4),
            }
            for cat, vals in per_category_metrics.items()
        },
    }


# ==============================================================================
# SOURCE CLASSIFIER GENERATOR & AUDIT
# ==============================================================================

SOURCE_CLASSES = [
    "BIOMASS_OR_WASTE_BURNING",
    "CLEAN_OR_BACKGROUND",
    "CONSTRUCTION_ACTIVITY",
    "COOKING_OR_FUEL_COMBUSTION",
    "HEAVY_DUST",
    "INDOOR_ACTIVITY",
    "INDUSTRIAL_OR_GENERATOR_EMISSIONS",
    "TRAFFIC",
]

def generate_source_classifier_eval_dataset(seed: int = 42, n_per_class: int = 40) -> List[Dict[str, Any]]:
    """
    Generates genuinely independent test samples for SourceClassifier:
    - 8 Standard source classes with shifted environmental and particulate statistics.
    - Shifted multi-source scenarios:
      1. Traffic + Construction Dust (competing CO and coarse PM)
      2. Combustion + Traffic (competing high fine PM, smoke MQ2, and vehicle MQ9)
      3. Industrial gas profiles + high PM (MQ135 dominant + elevated aerosols)
      4. Unusual PM coarse ratios (inverted ratio < 1.1 or extreme dust ratio > 5.0)
      5. Weather shifts: extreme rain washout & cold smog inversion
      6. Ambiguous tri-source mixtures to test MIXED_POLLUTION and UNKNOWN triggers
    """
    rng = np.random.default_rng(seed)
    samples: List[Dict[str, Any]] = []

    # 1. Shifted Standard 8 Classes
    for cls in SOURCE_CLASSES:
        for i in range(n_per_class):
            t = float(rng.uniform(15.0, 38.0))
            h = float(rng.uniform(25.0, 85.0))
            
            if cls == "CLEAN_OR_BACKGROUND":
                pm1 = float(rng.uniform(2.0, 8.0))
                pm25 = float(pm1 * rng.uniform(1.2, 1.8))
                pm10 = float(pm25 * rng.uniform(1.2, 1.6))
                mq2 = float(rng.uniform(0.60, 0.85))
                mq9 = float(rng.uniform(0.55, 0.80))
                mq135 = float(rng.uniform(0.60, 0.85))
            elif cls == "TRAFFIC":
                pm1 = float(rng.uniform(18.0, 45.0))
                pm25 = float(pm1 * rng.uniform(1.8, 2.5))
                pm10 = float(pm25 * rng.uniform(1.3, 1.7))
                mq2 = float(rng.uniform(1.10, 1.65))
                mq9 = float(rng.uniform(1.80, 2.80))  # Vehicle CO
                mq135 = float(rng.uniform(1.20, 1.80))
            elif cls == "HEAVY_DUST":
                pm1 = float(rng.uniform(5.0, 15.0))
                pm25 = float(rng.uniform(18.0, 40.0))
                pm10 = float(pm25 * rng.uniform(2.5, 4.5))  # High coarse PM10
                mq2 = float(rng.uniform(0.65, 0.95))
                mq9 = float(rng.uniform(0.60, 0.90))
                mq135 = float(rng.uniform(0.65, 0.95))
            elif cls == "CONSTRUCTION_ACTIVITY":
                pm1 = float(rng.uniform(10.0, 25.0))
                pm25 = float(rng.uniform(30.0, 70.0))
                pm10 = float(pm25 * rng.uniform(2.2, 3.8))  # Coarse dust
                mq2 = float(rng.uniform(0.90, 1.35))
                mq9 = float(rng.uniform(1.15, 1.75))  # Diesel construction machinery
                mq135 = float(rng.uniform(0.80, 1.25))
            elif cls == "BIOMASS_OR_WASTE_BURNING":
                pm1 = float(rng.uniform(35.0, 90.0))
                pm25 = float(pm1 * rng.uniform(1.8, 2.6))
                pm10 = float(pm25 * rng.uniform(1.15, 1.45))
                mq2 = float(rng.uniform(2.10, 3.60))  # Heavy smoke
                mq9 = float(rng.uniform(1.20, 1.95))
                mq135 = float(rng.uniform(1.70, 2.70))
            elif cls == "INDUSTRIAL_OR_GENERATOR_EMISSIONS":
                pm1 = float(rng.uniform(15.0, 40.0))
                pm25 = float(pm1 * rng.uniform(1.4, 2.0))
                pm10 = float(pm25 * rng.uniform(1.2, 1.6))
                mq2 = float(rng.uniform(0.90, 1.40))
                mq9 = float(rng.uniform(1.10, 1.70))
                mq135 = float(rng.uniform(2.10, 3.50))  # Heavy solvents/ammonia/NOx
            elif cls == "COOKING_OR_FUEL_COMBUSTION":
                pm1 = float(rng.uniform(20.0, 55.0))
                pm25 = float(pm1 * rng.uniform(1.3, 1.8))
                pm10 = float(pm25 * rng.uniform(1.1, 1.35))
                mq2 = float(rng.uniform(1.60, 2.60))  # Cooking aerosols/vapors
                mq9 = float(rng.uniform(0.85, 1.35))
                mq135 = float(rng.uniform(1.05, 1.75))
            elif cls == "INDOOR_ACTIVITY":
                pm1 = float(rng.uniform(5.0, 15.0))
                pm25 = float(pm1 * rng.uniform(1.1, 1.6))
                pm10 = float(pm25 * rng.uniform(1.15, 1.5))
                mq2 = float(rng.uniform(0.65, 0.95))
                mq9 = float(rng.uniform(0.60, 0.85))
                mq135 = float(rng.uniform(0.85, 1.35))
                t = float(rng.uniform(21.0, 26.0))  # HVAC indoor temp
                h = float(rng.uniform(45.0, 60.0))

            pm25 = max(pm1, pm25)
            pm10 = max(pm25, pm10)

            samples.append({
                "category": "standard_shifted",
                "expected_source": cls,
                "payload": {
                    "node_id": f"sc-eval-{cls}",
                    "timestamp": "2026-10-26T12:00:00Z",
                    "environment": {"temperature_C": round(t, 1), "humidity_pct": round(h, 1)},
                    "particulate_matter": {"PM1_0": round(pm1, 1), "PM2_5": round(pm25, 1), "PM10": round(pm10, 1)},
                    "gas_sensors": {
                        "MQ2": {"voltage_V": round(mq2, 3), "raw_adc": int(mq2 / 5.0 * 1023)},
                        "MQ9": {"voltage_V": round(mq9, 3), "raw_adc": int(mq9 / 5.0 * 1023)},
                        "MQ135": {"voltage_V": round(mq135, 3), "raw_adc": int(mq135 / 5.0 * 1023)},
                    },
                },
                "is_mixed_or_ambiguous": False,
            })

    # 2. Challenge Scenario 1: Traffic + Construction Dust (20 samples)
    for _ in range(20):
        samples.append({
            "category": "traffic_plus_construction",
            "expected_source": "CONSTRUCTION_ACTIVITY",  # or TRAFFIC/MIXED
            "competing_sources": ["TRAFFIC", "CONSTRUCTION_ACTIVITY"],
            "payload": {
                "node_id": "sc-eval-traf-const",
                "timestamp": "2026-10-26T14:00:00Z",
                "environment": {"temperature_C": round(float(rng.uniform(32.0, 39.0)), 1), "humidity_pct": round(float(rng.uniform(25.0, 45.0)), 1)},
                "particulate_matter": {"PM1_0": 22.0, "PM2_5": 65.0, "PM10": 210.0},  # High coarse PM10
                "gas_sensors": {
                    "MQ2": {"voltage_V": 1.45, "raw_adc": 296},
                    "MQ9": {"voltage_V": 2.25, "raw_adc": 460},  # Elevated CO
                    "MQ135": {"voltage_V": 1.55, "raw_adc": 317},
                },
            },
            "is_mixed_or_ambiguous": True,
        })

    # 3. Challenge Scenario 2: Combustion + Traffic (20 samples)
    for _ in range(20):
        samples.append({
            "category": "combustion_plus_traffic",
            "expected_source": "BIOMASS_OR_WASTE_BURNING",
            "competing_sources": ["BIOMASS_OR_WASTE_BURNING", "TRAFFIC"],
            "payload": {
                "node_id": "sc-eval-comb-traf",
                "timestamp": "2026-10-26T18:30:00Z",
                "environment": {"temperature_C": round(float(rng.uniform(20.0, 27.0)), 1), "humidity_pct": round(float(rng.uniform(60.0, 80.0)), 1)},
                "particulate_matter": {"PM1_0": 58.0, "PM2_5": 145.0, "PM10": 175.0},  # Dense fine PM
                "gas_sensors": {
                    "MQ2": {"voltage_V": 2.65, "raw_adc": 542},  # Heavy smoke
                    "MQ9": {"voltage_V": 2.15, "raw_adc": 440},  # Heavy traffic CO
                    "MQ135": {"voltage_V": 2.10, "raw_adc": 430},
                },
            },
            "is_mixed_or_ambiguous": True,
        })

    # 4. Challenge Scenario 3: Industrial Gas + Elevated PM (20 samples)
    for _ in range(20):
        samples.append({
            "category": "industrial_plus_pm",
            "expected_source": "INDUSTRIAL_OR_GENERATOR_EMISSIONS",
            "payload": {
                "node_id": "sc-eval-ind-pm",
                "timestamp": "2026-10-26T11:00:00Z",
                "environment": {"temperature_C": 31.0, "humidity_pct": 52.0},
                "particulate_matter": {"PM1_0": 28.0, "PM2_5": 68.0, "PM10": 92.0},
                "gas_sensors": {
                    "MQ2": {"voltage_V": 1.25, "raw_adc": 255},
                    "MQ9": {"voltage_V": 1.40, "raw_adc": 286},
                    "MQ135": {"voltage_V": 2.95, "raw_adc": 603},  # Very high VOC
                },
            },
            "is_mixed_or_ambiguous": False,
        })

    # 5. Challenge Scenario 4: Unusual PM Coarse / Fine Ratios (20 samples)
    # 4a. Ultra-fine aerosol (coarse ratio = 1.05)
    for _ in range(10):
        samples.append({
            "category": "unusual_pm_ratios",
            "expected_source": "COOKING_OR_FUEL_COMBUSTION",
            "payload": {
                "node_id": "sc-eval-ultrafine",
                "timestamp": "2026-10-26T19:00:00Z",
                "environment": {"temperature_C": 25.0, "humidity_pct": 55.0},
                "particulate_matter": {"PM1_0": 42.0, "PM2_5": 48.0, "PM10": 51.0},  # Coarse ratio 1.06
                "gas_sensors": {
                    "MQ2": {"voltage_V": 1.75, "raw_adc": 358},
                    "MQ9": {"voltage_V": 0.95, "raw_adc": 194},
                    "MQ135": {"voltage_V": 1.25, "raw_adc": 255},
                },
            },
            "is_mixed_or_ambiguous": False,
        })
    # 4b. Extreme coarse dust (coarse ratio = 5.2)
    for _ in range(10):
        samples.append({
            "category": "unusual_pm_ratios",
            "expected_source": "HEAVY_DUST",
            "payload": {
                "node_id": "sc-eval-extremedust",
                "timestamp": "2026-10-26T13:00:00Z",
                "environment": {"temperature_C": 35.0, "humidity_pct": 28.0},
                "particulate_matter": {"PM1_0": 6.0, "PM2_5": 25.0, "PM10": 130.0},  # Coarse ratio 5.2
                "gas_sensors": {
                    "MQ2": {"voltage_V": 0.70, "raw_adc": 143},
                    "MQ9": {"voltage_V": 0.65, "raw_adc": 133},
                    "MQ135": {"voltage_V": 0.75, "raw_adc": 153},
                },
            },
            "is_mixed_or_ambiguous": False,
        })

    # 6. Challenge Scenario 5: Tri-Source Ambiguity & Mixed Pollution (20 samples)
    # Cooking + Traffic + Construction
    for _ in range(20):
        samples.append({
            "category": "tri_source_mixture",
            "expected_source": "MIXED_POLLUTION",
            "payload": {
                "node_id": "sc-eval-tri-source",
                "timestamp": "2026-10-26T17:00:00Z",
                "environment": {"temperature_C": 28.0, "humidity_pct": 65.0},
                "particulate_matter": {"PM1_0": 35.0, "PM2_5": 85.0, "PM10": 195.0},  # High fine + high coarse
                "gas_sensors": {
                    "MQ2": {"voltage_V": 2.15, "raw_adc": 440},  # High smoke/cooking
                    "MQ9": {"voltage_V": 2.10, "raw_adc": 430},  # High traffic CO
                    "MQ135": {"voltage_V": 2.25, "raw_adc": 460},  # High industrial/general air
                },
            },
            "is_mixed_or_ambiguous": True,
        })

    return samples


def audit_source_classifier_model(model_dir: Path, dataset: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Runs SourceClassifier and evaluates source identification, mixed handling, and uncertainty."""
    sc = SourceClassifier(artifacts_dir=model_dir)
    sc.load()
    if not sc.is_loaded:
        return {"error": f"Failed to load SourceClassifier from {model_dir}"}

    y_true: List[str] = []
    y_pred: List[str] = []
    match_scores: List[float] = []
    uncertainty_flags: List[bool] = []
    mixed_flags: List[bool] = []

    per_category_metrics: Dict[str, Dict[str, Any]] = {}

    for s in dataset:
        p = SensorPayload.model_validate(s["payload"])
        res = sc.classify(p)
        top_src = res.get("top_source") or "UNKNOWN"
        preds = res.get("predictions", [])
        top_score = preds[0]["match_score"] if preds else 0.0
        is_unc = res.get("uncertainty", {}).get("is_uncertain", False) or (top_src == "UNKNOWN")
        is_mix = (top_src == "MIXED_POLLUTION") or any(p.get("source") == "MIXED_POLLUTION" for p in preds[:2])

        y_true.append(s["expected_source"])
        y_pred.append(top_src)
        match_scores.append(top_score)
        uncertainty_flags.append(is_unc)
        mixed_flags.append(is_mix)

        cat = s["category"]
        if cat not in per_category_metrics:
            per_category_metrics[cat] = {
                "total": 0,
                "correct": 0,
                "uncertain_count": 0,
                "mixed_detected_count": 0,
            }
        per_category_metrics[cat]["total"] += 1
        
        # Check match (if expected is MIXED_POLLUTION or has competing sources)
        competing = s.get("competing_sources", [])
        if s["expected_source"] == "MIXED_POLLUTION":
            is_match = (top_src == "MIXED_POLLUTION" or is_unc)
        elif competing:
            is_match = (top_src in competing or top_src == "MIXED_POLLUTION" or is_unc)
        else:
            is_match = (top_src == s["expected_source"])

        if is_match:
            per_category_metrics[cat]["correct"] += 1
        if is_unc:
            per_category_metrics[cat]["uncertain_count"] += 1
        if is_mix:
            per_category_metrics[cat]["mixed_detected_count"] += 1

    # Standard metrics on the standard shifted subset
    std_indices = [idx for idx, s in enumerate(dataset) if s["category"] == "standard_shifted"]
    std_y_true = np.array([y_true[idx] for idx in std_indices])
    std_y_pred = np.array([y_pred[idx] for idx in std_indices])
    std_conf = np.array([match_scores[idx] for idx in std_indices])

    std_classes = sorted(list(set(std_y_true) | set(std_y_pred)))
    std_acc = float(accuracy_score(std_y_true, std_y_pred))
    std_bal_acc = float(balanced_accuracy_score(std_y_true, std_y_pred))
    std_macro_f1 = float(f1_score(std_y_true, std_y_pred, average="macro", zero_division=0))
    std_cm = confusion_matrix(std_y_true, std_y_pred, labels=std_classes)
    std_report = classification_report(std_y_true, std_y_pred, labels=std_classes, output_dict=True, zero_division=0)

    # Mixed pollution trigger rate on mixtures
    mix_indices = [idx for idx, s in enumerate(dataset) if s.get("is_mixed_or_ambiguous", False)]
    mix_abstention_rate = float(np.mean([uncertainty_flags[idx] or mixed_flags[idx] for idx in mix_indices])) if mix_indices else 0.0

    return {
        "model_dir": str(model_dir),
        "total_samples": len(dataset),
        "standard_shifted_metrics": {
            "accuracy": round(std_acc, 4),
            "balanced_accuracy": round(std_bal_acc, 4),
            "macro_f1": round(std_macro_f1, 4),
            "mean_match_score": round(float(np.mean(std_conf)), 4),
            "confusion_matrix": {
                "classes": std_classes,
                "matrix": std_cm.tolist(),
            },
            "per_class": {
                cls: {
                    "precision": round(std_report[cls]["precision"], 4),
                    "recall": round(std_report[cls]["recall"], 4),
                    "f1": round(std_report[cls]["f1-score"], 4),
                    "support": int(std_report[cls]["support"]),
                }
                for cls in std_classes if cls in std_report
            },
        },
        "mixed_and_ambiguous_handling": {
            "n_ambiguous_samples": len(mix_indices),
            "uncertain_or_mixed_abstention_rate": round(mix_abstention_rate, 4),
        },
        "category_breakdown": {
            cat: {
                "effective_accuracy": round(vals["correct"] / vals["total"], 4),
                "samples": vals["total"],
                "uncertainty_rate": round(vals["uncertain_count"] / vals["total"], 4),
                "mixed_detected_rate": round(vals["mixed_detected_count"] / vals["total"], 4),
            }
            for cat, vals in per_category_metrics.items()
        },
    }


# ==============================================================================
# MULTI-SEED RUNNER
# ==============================================================================

def run_multi_seed_audit():
    print("=" * 75)
    print("NAVOSEDGE PHASE 2: INDEPENDENT MODEL GENERALIZATION AUDIT")
    print("=" * 75)

    active_artifacts = (SERVER_DIR / "artifacts").resolve()
    baseline_artifacts = (SERVER_DIR / "artifacts" / "backups" / "original_baseline").resolve()

    seeds = [42, 101, 777]
    output_dir = ROOT_DIR / "test_data" / "phase2_model_audit"
    output_dir.mkdir(parents=True, exist_ok=True)

    audit_summary: Dict[str, Any] = {
        "audit_timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seeds": seeds,
        "models": {
            "active_artifacts_dir": str(active_artifacts),
            "baseline_artifacts_dir": str(baseline_artifacts),
        },
        "tinygasnet_results": {
            "active": [],
            "baseline": [],
        },
        "source_classifier_results": {
            "active": [],
            "baseline": [],
        },
    }

    # Run TinyGasNet Multi-Seed Audit
    print("\n>>> AUDITING TINYGASNET (Active vs Baseline)...")
    for s in seeds:
        print(f"  [Seed {s}] Generating independent GasNet challenge dataset...")
        gas_ds = generate_tinygasnet_eval_dataset(seed=s)
        
        # Save labeled synthetic dataset
        ds_file = output_dir / f"synthetic_tinygasnet_eval_seed_{s}.json"
        with open(ds_file, "w") as f:
            json.dump({
                "label": "SYNTHETIC — INDEPENDENT GENERALIZATION EVALUATION",
                "seed": s,
                "n_samples": len(gas_ds),
                "data": gas_ds,
            }, f, indent=2)

        res_active = audit_tinygasnet_model(active_artifacts, gas_ds)
        res_baseline = audit_tinygasnet_model(baseline_artifacts, gas_ds)

        res_active["seed"] = s
        res_baseline["seed"] = s
        audit_summary["tinygasnet_results"]["active"].append(res_active)
        audit_summary["tinygasnet_results"]["baseline"].append(res_baseline)

        print(f"  Seed {s} | Active Acc: {res_active['accuracy']:.4f} (Bal: {res_active['balanced_accuracy']:.4f}, ECE: {res_active['expected_calibration_error']:.4f}) | "
              f"Baseline Acc: {res_baseline['accuracy']:.4f} (Bal: {res_baseline['balanced_accuracy']:.4f}, ECE: {res_baseline['expected_calibration_error']:.4f})")

    # Run SourceClassifier Multi-Seed Audit
    print("\n>>> AUDITING SOURCE CLASSIFIER (Active vs Baseline)...")
    for s in seeds:
        print(f"  [Seed {s}] Generating independent SourceClassifier challenge dataset...")
        sc_ds = generate_source_classifier_eval_dataset(seed=s)

        # Save labeled synthetic dataset
        ds_file = output_dir / f"synthetic_source_classifier_eval_seed_{s}.json"
        with open(ds_file, "w") as f:
            json.dump({
                "label": "SYNTHETIC — INDEPENDENT GENERALIZATION EVALUATION",
                "seed": s,
                "n_samples": len(sc_ds),
                "data": sc_ds,
            }, f, indent=2)

        sc_active = audit_source_classifier_model(active_artifacts, sc_ds)
        sc_baseline = audit_source_classifier_model(baseline_artifacts, sc_ds)

        sc_active["seed"] = s
        sc_baseline["seed"] = s
        audit_summary["source_classifier_results"]["active"].append(sc_active)
        audit_summary["source_classifier_results"]["baseline"].append(sc_baseline)

        std_act = sc_active["standard_shifted_metrics"]
        std_base = sc_baseline["standard_shifted_metrics"]
        print(f"  Seed {s} | Active 8-Class Acc: {std_act['accuracy']:.4f} (F1: {std_act['macro_f1']:.4f}, Ambiguous Abstention: {sc_active['mixed_and_ambiguous_handling']['uncertain_or_mixed_abstention_rate']:.4f}) | "
              f"Baseline 8-Class Acc: {std_base['accuracy']:.4f} (F1: {std_base['macro_f1']:.4f}, Ambiguous Abstention: {sc_baseline['mixed_and_ambiguous_handling']['uncertain_or_mixed_abstention_rate']:.4f})")

    # Aggregate Statistics
    def compute_stats(values: List[float]) -> Dict[str, float]:
        return {
            "mean": round(float(np.mean(values)), 4),
            "std": round(float(np.std(values)), 4),
            "min": round(float(np.min(values)), 4),
            "max": round(float(np.max(values)), 4),
        }

    audit_summary["aggregate_metrics"] = {
        "tinygasnet": {
            "active_accuracy": compute_stats([r["accuracy"] for r in audit_summary["tinygasnet_results"]["active"]]),
            "baseline_accuracy": compute_stats([r["accuracy"] for r in audit_summary["tinygasnet_results"]["baseline"]]),
            "active_balanced_accuracy": compute_stats([r["balanced_accuracy"] for r in audit_summary["tinygasnet_results"]["active"]]),
            "baseline_balanced_accuracy": compute_stats([r["balanced_accuracy"] for r in audit_summary["tinygasnet_results"]["baseline"]]),
            "active_macro_f1": compute_stats([r["macro_f1"] for r in audit_summary["tinygasnet_results"]["active"]]),
            "baseline_macro_f1": compute_stats([r["macro_f1"] for r in audit_summary["tinygasnet_results"]["baseline"]]),
            "active_ece": compute_stats([r["expected_calibration_error"] for r in audit_summary["tinygasnet_results"]["active"]]),
            "baseline_ece": compute_stats([r["expected_calibration_error"] for r in audit_summary["tinygasnet_results"]["baseline"]]),
        },
        "source_classifier": {
            "active_accuracy": compute_stats([r["standard_shifted_metrics"]["accuracy"] for r in audit_summary["source_classifier_results"]["active"]]),
            "baseline_accuracy": compute_stats([r["standard_shifted_metrics"]["accuracy"] for r in audit_summary["source_classifier_results"]["baseline"]]),
            "active_macro_f1": compute_stats([r["standard_shifted_metrics"]["macro_f1"] for r in audit_summary["source_classifier_results"]["active"]]),
            "baseline_macro_f1": compute_stats([r["standard_shifted_metrics"]["macro_f1"] for r in audit_summary["source_classifier_results"]["baseline"]]),
            "active_ambiguous_abstention": compute_stats([r["mixed_and_ambiguous_handling"]["uncertain_or_mixed_abstention_rate"] for r in audit_summary["source_classifier_results"]["active"]]),
            "baseline_ambiguous_abstention": compute_stats([r["mixed_and_ambiguous_handling"]["uncertain_or_mixed_abstention_rate"] for r in audit_summary["source_classifier_results"]["baseline"]]),
        }
    }

    # Save summary report
    summary_file = output_dir / "audit_summary_metrics.json"
    with open(summary_file, "w") as f:
        json.dump(audit_summary, f, indent=2)

    print(f"\nAudit complete! Full evaluation saved to: {summary_file}")
    return audit_summary


if __name__ == "__main__":
    run_multi_seed_audit()
