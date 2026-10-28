from datetime import datetime, timezone
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "Intelligence" / "Server"))

from app.schemas.sensor import SensorPayload
from app.source_classifier.classifier import SourceClassifier
from app.source_classifier.categories import SourceCategory

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

def generate_eval_dataset(seed: int = 42, n_per_class: int = 40) -> List[Dict[str, Any]]:
    rng = np.random.default_rng(seed)
    samples: List[Dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Shifted Standard 8 Classes (320 samples)
    for cls in SOURCE_CLASSES:
        for _ in range(n_per_class):
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
                mq9 = float(rng.uniform(1.80, 2.80))
                mq135 = float(rng.uniform(1.20, 1.80))
            elif cls == "HEAVY_DUST":
                pm1 = float(rng.uniform(5.0, 15.0))
                pm25 = float(rng.uniform(18.0, 40.0))
                pm10 = float(pm25 * rng.uniform(2.5, 4.5))
                mq2 = float(rng.uniform(0.65, 0.95))
                mq9 = float(rng.uniform(0.60, 0.90))
                mq135 = float(rng.uniform(0.65, 0.95))
            elif cls == "CONSTRUCTION_ACTIVITY":
                pm1 = float(rng.uniform(10.0, 25.0))
                pm25 = float(rng.uniform(30.0, 70.0))
                pm10 = float(pm25 * rng.uniform(2.2, 3.8))
                mq2 = float(rng.uniform(0.90, 1.35))
                mq9 = float(rng.uniform(1.15, 1.75))
                mq135 = float(rng.uniform(0.80, 1.25))
            elif cls == "BIOMASS_OR_WASTE_BURNING":
                pm1 = float(rng.uniform(35.0, 90.0))
                pm25 = float(pm1 * rng.uniform(1.8, 2.6))
                pm10 = float(pm25 * rng.uniform(1.15, 1.45))
                mq2 = float(rng.uniform(2.10, 3.60))
                mq9 = float(rng.uniform(1.20, 1.95))
                mq135 = float(rng.uniform(1.70, 2.70))
            elif cls == "INDUSTRIAL_OR_GENERATOR_EMISSIONS":
                pm1 = float(rng.uniform(15.0, 40.0))
                pm25 = float(pm1 * rng.uniform(1.4, 2.0))
                pm10 = float(pm25 * rng.uniform(1.2, 1.6))
                mq2 = float(rng.uniform(0.90, 1.40))
                mq9 = float(rng.uniform(1.10, 1.70))
                mq135 = float(rng.uniform(2.10, 3.50))
            elif cls == "COOKING_OR_FUEL_COMBUSTION":
                pm1 = float(rng.uniform(20.0, 55.0))
                pm25 = float(pm1 * rng.uniform(1.3, 1.8))
                pm10 = float(pm25 * rng.uniform(1.1, 1.35))
                mq2 = float(rng.uniform(1.60, 2.60))
                mq9 = float(rng.uniform(0.85, 1.35))
                mq135 = float(rng.uniform(1.05, 1.75))
            elif cls == "INDOOR_ACTIVITY":
                pm1 = float(rng.uniform(5.0, 15.0))
                pm25 = float(pm1 * rng.uniform(1.1, 1.6))
                pm10 = float(pm25 * rng.uniform(1.15, 1.5))
                mq2 = float(rng.uniform(0.65, 0.95))
                mq9 = float(rng.uniform(0.60, 0.85))
                mq135 = float(rng.uniform(0.85, 1.35))
                t = float(rng.uniform(21.0, 26.0))
                h = float(rng.uniform(45.0, 60.0))

            pm25 = max(pm1, pm25)
            pm10 = max(pm25, pm10)

            samples.append({
                "category": "standard_shifted",
                "expected_source": cls,
                "payload": {
                    "node_id": f"eval-{cls}",
                    "timestamp": now_iso,
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

    # 2. Dual Mixture: Traffic + Construction Dust (20 samples)
    for _ in range(20):
        samples.append({
            "category": "traffic_plus_construction",
            "expected_source": "MIXED_POLLUTION",
            "competing_sources": ["TRAFFIC", "CONSTRUCTION_ACTIVITY"],
            "payload": {
                "node_id": "eval-traf-const",
                "timestamp": now_iso,
                "environment": {"temperature_C": 34.0, "humidity_pct": 35.0},
                "particulate_matter": {"PM1_0": 22.0, "PM2_5": 65.0, "PM10": 210.0},
                "gas_sensors": {
                    "MQ2": {"voltage_V": 1.45, "raw_adc": 296},
                    "MQ9": {"voltage_V": 2.25, "raw_adc": 460},
                    "MQ135": {"voltage_V": 1.55, "raw_adc": 317},
                },
            },
            "is_mixed_or_ambiguous": True,
        })

    # 3. Dual Mixture: Combustion Smoke + Traffic (20 samples)
    for _ in range(20):
        samples.append({
            "category": "combustion_plus_traffic",
            "expected_source": "MIXED_POLLUTION",
            "competing_sources": ["BIOMASS_OR_WASTE_BURNING", "TRAFFIC"],
            "payload": {
                "node_id": "eval-comb-traf",
                "timestamp": now_iso,
                "environment": {"temperature_C": 23.0, "humidity_pct": 70.0},
                "particulate_matter": {"PM1_0": 58.0, "PM2_5": 145.0, "PM10": 175.0},
                "gas_sensors": {
                    "MQ2": {"voltage_V": 2.65, "raw_adc": 542},
                    "MQ9": {"voltage_V": 2.15, "raw_adc": 440},
                    "MQ135": {"voltage_V": 2.10, "raw_adc": 430},
                },
            },
            "is_mixed_or_ambiguous": True,
        })

    # 4. Dual Mixture: Industrial Gas + Dust (20 samples)
    for _ in range(20):
        samples.append({
            "category": "industrial_plus_pm",
            "expected_source": "MIXED_POLLUTION",
            "competing_sources": ["INDUSTRIAL_OR_GENERATOR_EMISSIONS", "HEAVY_DUST"],
            "payload": {
                "node_id": "eval-ind-pm",
                "timestamp": now_iso,
                "environment": {"temperature_C": 31.0, "humidity_pct": 52.0},
                "particulate_matter": {"PM1_0": 28.0, "PM2_5": 68.0, "PM10": 192.0},
                "gas_sensors": {
                    "MQ2": {"voltage_V": 1.25, "raw_adc": 255},
                    "MQ9": {"voltage_V": 1.40, "raw_adc": 286},
                    "MQ135": {"voltage_V": 2.95, "raw_adc": 603},
                },
            },
            "is_mixed_or_ambiguous": True,
        })

    # 5. Tri-Source Mixture (20 samples)
    for _ in range(20):
        samples.append({
            "category": "tri_source_mixture",
            "expected_source": "MIXED_POLLUTION",
            "competing_sources": ["COOKING_OR_FUEL_COMBUSTION", "TRAFFIC", "CONSTRUCTION_ACTIVITY"],
            "payload": {
                "node_id": "eval-tri-source",
                "timestamp": now_iso,
                "environment": {"temperature_C": 28.0, "humidity_pct": 65.0},
                "particulate_matter": {"PM1_0": 35.0, "PM2_5": 85.0, "PM10": 195.0},
                "gas_sensors": {
                    "MQ2": {"voltage_V": 2.15, "raw_adc": 440},
                    "MQ9": {"voltage_V": 2.10, "raw_adc": 430},
                    "MQ135": {"voltage_V": 2.25, "raw_adc": 460},
                },
            },
            "is_mixed_or_ambiguous": True,
        })

    return samples


def evaluate_classifier(sc: SourceClassifier, dataset: List[Dict[str, Any]]) -> Dict[str, Any]:
    y_true = []
    y_pred = []
    is_uncertain_list = []
    is_mixed_list = []
    conf_list = []

    mix_categories = {"traffic_plus_construction", "combustion_plus_traffic", "industrial_plus_pm", "tri_source_mixture"}
    mix_total = 0
    mix_detected = 0

    ambiguous_traffic_ind_total = 0
    ambiguous_traffic_ind_flagged = 0

    ambiguous_indoor_clean_total = 0
    ambiguous_indoor_clean_flagged = 0

    for s in dataset:
        payload = SensorPayload.model_validate(s["payload"])
        res = sc.classify(payload)
        top = res.get("top_source") or "UNKNOWN"
        unc = res.get("uncertainty", {}).get("is_uncertain", False)
        preds = res.get("predictions", [])
        top_conf = preds[0].get("confidence") if preds else None

        y_true.append(s["expected_source"])
        y_pred.append(top)
        is_uncertain_list.append(unc)
        is_mixed_list.append(top == "MIXED_POLLUTION" or any(p.get("source") == "MIXED_POLLUTION" for p in preds[:2]))
        if top_conf is not None:
            conf_list.append(top_conf)

        if s["category"] in mix_categories:
            mix_total += 1
            if top == "MIXED_POLLUTION" or (unc and any(p.get("source") == "MIXED_POLLUTION" for p in preds[:2])):
                mix_detected += 1

        # Check ambiguity tracking
        exp = s["expected_source"]
        if exp in ("TRAFFIC", "INDUSTRIAL_OR_GENERATOR_EMISSIONS"):
            ambiguous_traffic_ind_total += 1
            if unc:
                ambiguous_traffic_ind_flagged += 1
        elif exp in ("INDOOR_ACTIVITY", "CLEAN_OR_BACKGROUND"):
            ambiguous_indoor_clean_total += 1
            if unc:
                ambiguous_indoor_clean_flagged += 1

    std_idx = [i for i, s in enumerate(dataset) if s["category"] == "standard_shifted"]
    std_true = [y_true[i] for i in std_idx]
    std_pred = [y_pred[i] for i in std_idx]

    labels = SOURCE_CLASSES
    report = classification_report(std_true, std_pred, labels=labels, output_dict=True, zero_division=0)
    cm = confusion_matrix(std_true, std_pred, labels=labels).tolist()

    return {
        "accuracy": accuracy_score(std_true, std_pred),
        "macro_f1": f1_score(std_true, std_pred, average="macro", zero_division=0),
        "per_class": {k: report[k] for k in labels if k in report},
        "confusion_matrix": cm,
        "classes": labels,
        "mixed_detection_rate": mix_detected / mix_total if mix_total else 0.0,
        "traffic_ind_uncertainty_rate": ambiguous_traffic_ind_flagged / ambiguous_traffic_ind_total if ambiguous_traffic_ind_total else 0.0,
        "indoor_clean_uncertainty_rate": ambiguous_indoor_clean_flagged / ambiguous_indoor_clean_total if ambiguous_indoor_clean_total else 0.0,
        "mean_confidence": float(np.mean(conf_list)) if conf_list else 0.0,
    }


if __name__ == "__main__":
    artifacts_dir = Path("Intelligence/Server/artifacts")
    sc = SourceClassifier(artifacts_dir=artifacts_dir)
    sc.load()

    all_seeds_results = []
    for seed in [42, 101, 777]:
        ds = generate_eval_dataset(seed=seed)
        r = evaluate_classifier(sc, ds)
        r["seed"] = seed
        all_seeds_results.append(r)
        print(f"Seed {seed}: Acc={r['accuracy']:.4f}, Macro-F1={r['macro_f1']:.4f}, MixedDetection={r['mixed_detection_rate']:.4f}, TrafficIndUncertainty={r['traffic_ind_uncertainty_rate']:.4f}, IndoorCleanUncertainty={r['indoor_clean_uncertainty_rate']:.4f}")

    mean_acc = float(np.mean([r["accuracy"] for r in all_seeds_results]))
    mean_f1 = float(np.mean([r["macro_f1"] for r in all_seeds_results]))
    mean_mix = float(np.mean([r["mixed_detection_rate"] for r in all_seeds_results]))
    mean_traf_ind_unc = float(np.mean([r["traffic_ind_uncertainty_rate"] for r in all_seeds_results]))
    mean_indoor_unc = float(np.mean([r["indoor_clean_uncertainty_rate"] for r in all_seeds_results]))

    # Average per-class metrics across seeds
    per_class_avg = {}
    for cls in SOURCE_CLASSES:
        prec = float(np.mean([r["per_class"][cls]["precision"] for r in all_seeds_results]))
        rec = float(np.mean([r["per_class"][cls]["recall"] for r in all_seeds_results]))
        f1 = float(np.mean([r["per_class"][cls]["f1-score"] for r in all_seeds_results]))
        per_class_avg[cls] = {"precision": prec, "recall": rec, "f1-score": f1}

    print("\n--- 3-SEED AGGREGATE BASELINE ---")
    print(f"Mean Standard Shifted Accuracy : {mean_acc:.4f}")
    print(f"Mean Macro-F1                  : {mean_f1:.4f}")
    print(f"Mean Mixed Pollution Detection : {mean_mix:.4f}")
    print(f"Traffic/Ind Uncertainty Rate   : {mean_traf_ind_unc:.4f}")
    print(f"Indoor/Clean Uncertainty Rate  : {mean_indoor_unc:.4f}")
    print("\nPer-Class Baseline Metrics:")
    for cls, m in per_class_avg.items():
        print(f"  {cls:35s}: P={m['precision']:.3f}, R={m['recall']:.3f}, F1={m['f1-score']:.3f}")

    # Compute sum confusion matrix
    cm_sum = np.sum([np.array(r["confusion_matrix"]) for r in all_seeds_results], axis=0).tolist()

    out_data = {
        "mean_accuracy": mean_acc,
        "mean_macro_f1": mean_f1,
        "mean_mixed_detection": mean_mix,
        "mean_traffic_ind_uncertainty": mean_traf_ind_unc,
        "mean_indoor_clean_uncertainty": mean_indoor_unc,
        "per_class": per_class_avg,
        "confusion_matrix_sum": cm_sum,
        "classes": SOURCE_CLASSES,
        "seeds": [42, 101, 777],
    }
    with open("scratch/baseline_eval_results.json", "w") as f:
        json.dump(out_data, f, indent=2)
    print("\nWrote baseline results to scratch/baseline_eval_results.json")
