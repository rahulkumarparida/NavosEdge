from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from typing import Any, Dict, List, Tuple

import numpy as np
from sklearn.metrics import classification_report, confusion_matrix, f1_score, accuracy_score

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


def generate_independent_scenarios(seed: int = 42, n_per_class: int = 40) -> List[Dict[str, Any]]:
    """
    Generate independent synthetic evaluation scenarios using shifted distributions,
    voltage drift, sensor noise, PM scaling variation, and dual/tri mixtures.
    All data is labeled synthetic.
    """
    rng = np.random.default_rng(seed)
    samples: List[Dict[str, Any]] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Shifted Standard 8 Classes (320 samples per seed)
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
                mq9 = float(rng.uniform(0.60, 0.85))
                mq135 = float(rng.uniform(0.70, 1.10))
            elif cls == "CONSTRUCTION_ACTIVITY":
                pm1 = float(rng.uniform(15.0, 35.0))
                pm25 = float(rng.uniform(40.0, 90.0))
                pm10 = float(pm25 * rng.uniform(2.0, 3.8))
                mq2 = float(rng.uniform(1.00, 1.40))
                mq9 = float(rng.uniform(1.30, 2.00))
                mq135 = float(rng.uniform(1.10, 1.60))
            elif cls == "BIOMASS_OR_WASTE_BURNING":
                pm1 = float(rng.uniform(40.0, 120.0))
                pm25 = float(pm1 * rng.uniform(1.8, 2.6))
                pm10 = float(pm25 * rng.uniform(1.1, 1.4))
                mq2 = float(rng.uniform(2.20, 3.80))
                mq9 = float(rng.uniform(1.60, 2.70))
                mq135 = float(rng.uniform(1.60, 2.80))
            elif cls == "INDUSTRIAL_OR_GENERATOR_EMISSIONS":
                pm1 = float(rng.uniform(20.0, 50.0))
                pm25 = float(pm1 * rng.uniform(1.6, 2.4))
                pm10 = float(pm25 * rng.uniform(1.2, 1.6))
                mq2 = float(rng.uniform(1.20, 1.90))
                mq9 = float(rng.uniform(1.70, 2.90))
                mq135 = float(rng.uniform(2.00, 3.40))
            elif cls == "COOKING_OR_FUEL_COMBUSTION":
                pm1 = float(rng.uniform(25.0, 70.0))
                pm25 = float(pm1 * rng.uniform(1.5, 2.2))
                pm10 = float(pm25 * rng.uniform(1.1, 1.4))
                mq2 = float(rng.uniform(2.00, 3.20))
                mq9 = float(rng.uniform(1.10, 1.70))
                mq135 = float(rng.uniform(1.20, 1.90))
            elif cls == "INDOOR_ACTIVITY":
                pm1 = float(rng.uniform(3.0, 12.0))
                pm25 = float(pm1 * rng.uniform(1.2, 1.8))
                pm10 = float(pm25 * rng.uniform(1.2, 1.7))
                mq2 = float(rng.uniform(0.65, 0.95))
                mq9 = float(rng.uniform(0.60, 0.85))
                mq135 = float(rng.uniform(0.85, 1.35))
                t = float(rng.uniform(21.0, 26.0))
                h = float(rng.uniform(45.0, 60.0))

            pm25 = max(pm1, pm25)
            pm10 = max(pm25, pm10)

            # Apply realistic voltage drift & noise
            drift = float(rng.normal(0.0, 0.02))
            mq2 = min(4.8, max(0.2, mq2 + drift))
            mq9 = min(4.8, max(0.2, mq9 + drift))
            mq135 = min(4.8, max(0.2, mq135 + drift))

            samples.append({
                "scenario_type": "standard_shifted",
                "expected_source": cls,
                "payload": {
                    "node_id": f"syn-{cls}",
                    "timestamp": now_iso,
                    "environment": {"temperature_C": round(t, 1), "humidity_pct": round(h, 1)},
                    "particulate_matter": {"PM1_0": round(pm1, 1), "PM2_5": round(pm25, 1), "PM10": round(pm10, 1)},
                    "gas_sensors": {
                        "MQ2": {"voltage_V": round(mq2, 3), "raw_adc": int(mq2 / 5.0 * 1023)},
                        "MQ9": {"voltage_V": round(mq9, 3), "raw_adc": int(mq9 / 5.0 * 1023)},
                        "MQ135": {"voltage_V": round(mq135, 3), "raw_adc": int(mq135 / 5.0 * 1023)},
                    },
                },
                "is_synthetic": True,
            })

    # 2. Dual Mixture: Traffic Exhaust + Construction Dust (20 samples)
    for _ in range(20):
        t_drift = float(rng.normal(0.0, 0.03))
        samples.append({
            "scenario_type": "traffic_plus_construction",
            "expected_source": "MIXED_POLLUTION",
            "competing_sources": ["TRAFFIC", "CONSTRUCTION_ACTIVITY"],
            "payload": {
                "node_id": "syn-traf-const",
                "timestamp": now_iso,
                "environment": {"temperature_C": 34.0, "humidity_pct": 35.0},
                "particulate_matter": {"PM1_0": 22.0, "PM2_5": 65.0, "PM10": 210.0},
                "gas_sensors": {
                    "MQ2": {"voltage_V": round(1.45 + t_drift, 3), "raw_adc": int((1.45 + t_drift) / 5.0 * 1023)},
                    "MQ9": {"voltage_V": round(2.25 + t_drift, 3), "raw_adc": int((2.25 + t_drift) / 5.0 * 1023)},
                    "MQ135": {"voltage_V": round(1.55 + t_drift, 3), "raw_adc": int((1.55 + t_drift) / 5.0 * 1023)},
                },
            },
            "is_synthetic": True,
        })

    # 3. Dual Mixture: Biomass Smoke + Traffic Exhaust (20 samples)
    for _ in range(20):
        t_drift = float(rng.normal(0.0, 0.03))
        samples.append({
            "scenario_type": "combustion_plus_traffic",
            "expected_source": "MIXED_POLLUTION",
            "competing_sources": ["BIOMASS_OR_WASTE_BURNING", "TRAFFIC"],
            "payload": {
                "node_id": "syn-comb-traf",
                "timestamp": now_iso,
                "environment": {"temperature_C": 23.0, "humidity_pct": 70.0},
                "particulate_matter": {"PM1_0": 58.0, "PM2_5": 145.0, "PM10": 175.0},
                "gas_sensors": {
                    "MQ2": {"voltage_V": round(2.65 + t_drift, 3), "raw_adc": int((2.65 + t_drift) / 5.0 * 1023)},
                    "MQ9": {"voltage_V": round(2.15 + t_drift, 3), "raw_adc": int((2.15 + t_drift) / 5.0 * 1023)},
                    "MQ135": {"voltage_V": round(2.10 + t_drift, 3), "raw_adc": int((2.10 + t_drift) / 5.0 * 1023)},
                },
            },
            "is_synthetic": True,
        })

    # 4. Dual Mixture: Industrial Gas + Heavy Dust (20 samples)
    for _ in range(20):
        t_drift = float(rng.normal(0.0, 0.03))
        samples.append({
            "scenario_type": "industrial_plus_pm",
            "expected_source": "MIXED_POLLUTION",
            "competing_sources": ["INDUSTRIAL_OR_GENERATOR_EMISSIONS", "HEAVY_DUST"],
            "payload": {
                "node_id": "syn-ind-pm",
                "timestamp": now_iso,
                "environment": {"temperature_C": 31.0, "humidity_pct": 52.0},
                "particulate_matter": {"PM1_0": 28.0, "PM2_5": 68.0, "PM10": 192.0},
                "gas_sensors": {
                    "MQ2": {"voltage_V": round(1.25 + t_drift, 3), "raw_adc": int((1.25 + t_drift) / 5.0 * 1023)},
                    "MQ9": {"voltage_V": round(1.40 + t_drift, 3), "raw_adc": int((1.40 + t_drift) / 5.0 * 1023)},
                    "MQ135": {"voltage_V": round(2.95 + t_drift, 3), "raw_adc": int((2.95 + t_drift) / 5.0 * 1023)},
                },
            },
            "is_synthetic": True,
        })

    # 5. Tri-Source Mixture (20 samples)
    for _ in range(20):
        t_drift = float(rng.normal(0.0, 0.03))
        samples.append({
            "scenario_type": "tri_source_mixture",
            "expected_source": "MIXED_POLLUTION",
            "competing_sources": ["COOKING_OR_FUEL_COMBUSTION", "TRAFFIC", "CONSTRUCTION_ACTIVITY"],
            "payload": {
                "node_id": "syn-tri-source",
                "timestamp": now_iso,
                "environment": {"temperature_C": 28.0, "humidity_pct": 65.0},
                "particulate_matter": {"PM1_0": 35.0, "PM2_5": 85.0, "PM10": 195.0},
                "gas_sensors": {
                    "MQ2": {"voltage_V": round(2.15 + t_drift, 3), "raw_adc": int((2.15 + t_drift) / 5.0 * 1023)},
                    "MQ9": {"voltage_V": round(2.10 + t_drift, 3), "raw_adc": int((2.10 + t_drift) / 5.0 * 1023)},
                    "MQ135": {"voltage_V": round(2.25 + t_drift, 3), "raw_adc": int((2.25 + t_drift) / 5.0 * 1023)},
                },
            },
            "is_synthetic": True,
        })

    return samples


def run_evaluation(sc: SourceClassifier, dataset: List[Dict[str, Any]]) -> Dict[str, Any]:
    y_true = []
    y_pred = []
    is_uncertain_list = []
    conf_list_ambiguous = []
    conf_list_unambiguous = []
    abstain_count = 0

    mixture_stats = {
        "traffic_plus_construction": {"total": 0, "detected": 0},
        "combustion_plus_traffic": {"total": 0, "detected": 0},
        "industrial_plus_pm": {"total": 0, "detected": 0},
        "tri_source_mixture": {"total": 0, "detected": 0},
    }

    traf_ind_total = 0
    traf_ind_uncertain = 0

    indoor_clean_total = 0
    indoor_clean_uncertain = 0

    for s in dataset:
        payload = SensorPayload.model_validate(s["payload"])
        res = sc.classify(payload)
        top = res.get("top_source") or "UNKNOWN"
        unc = res.get("uncertainty", {}).get("is_uncertain", False)
        preds = res.get("predictions", [])
        top_conf = preds[0].get("confidence") if preds else None

        stype = s["scenario_type"]
        exp = s["expected_source"]

        y_true.append(exp)
        y_pred.append(top)
        is_uncertain_list.append(unc)

        if top == "UNKNOWN":
            abstain_count += 1

        if stype in mixture_stats:
            mixture_stats[stype]["total"] += 1
            if top == "MIXED_POLLUTION":
                mixture_stats[stype]["detected"] += 1

        if exp in ("TRAFFIC", "INDUSTRIAL_OR_GENERATOR_EMISSIONS"):
            traf_ind_total += 1
            if unc:
                traf_ind_uncertain += 1
            if top_conf is not None:
                conf_list_ambiguous.append(top_conf)
        elif exp in ("INDOOR_ACTIVITY", "CLEAN_OR_BACKGROUND"):
            indoor_clean_total += 1
            if unc:
                indoor_clean_uncertain += 1
            if top_conf is not None:
                conf_list_ambiguous.append(top_conf)
        elif exp in ("HEAVY_DUST", "BIOMASS_OR_WASTE_BURNING"):
            if top_conf is not None:
                conf_list_unambiguous.append(top_conf)

    # Standard shifted evaluation metrics
    std_idx = [i for i, s in enumerate(dataset) if s["scenario_type"] == "standard_shifted"]
    std_true = [y_true[i] for i in std_idx]
    std_pred = [y_pred[i] for i in std_idx]

    labels = SOURCE_CLASSES
    report = classification_report(std_true, std_pred, labels=labels, output_dict=True, zero_division=0)
    cm = confusion_matrix(std_true, std_pred, labels=labels).tolist()

    total_mix = sum(v["total"] for v in mixture_stats.values())
    total_mix_det = sum(v["detected"] for v in mixture_stats.values())

    return {
        "accuracy": accuracy_score(std_true, std_pred),
        "macro_f1": f1_score(std_true, std_pred, average="macro", zero_division=0),
        "per_class": {k: report[k] for k in labels if k in report},
        "confusion_matrix": cm,
        "classes": labels,
        "abstention_rate": abstain_count / len(dataset),
        "mixture_detection_overall": total_mix_det / total_mix if total_mix else 0.0,
        "mixture_breakdown": {
            k: v["detected"] / v["total"] if v["total"] else 0.0
            for k, v in mixture_stats.items()
        },
        "traffic_ind_uncertainty_rate": traf_ind_uncertain / traf_ind_total if traf_ind_total else 0.0,
        "indoor_clean_uncertainty_rate": indoor_clean_uncertain / indoor_clean_total if indoor_clean_total else 0.0,
        "mean_conf_ambiguous": float(np.mean(conf_list_ambiguous)) if conf_list_ambiguous else 0.0,
        "mean_conf_unambiguous": float(np.mean(conf_list_unambiguous)) if conf_list_unambiguous else 0.0,
    }


if __name__ == "__main__":
    artifacts_dir = Path("Intelligence/Server/artifacts")
    sc = SourceClassifier(artifacts_dir=artifacts_dir)
    sc.load()

    # Pre-intervention baseline metrics (measured before Phase 2B changes)
    TRUE_BASELINE = {
        "mean_accuracy": 0.6292,
        "mean_macro_f1": 0.6160,
        "mixture_detection_rate": 0.0000,
        "traffic_ind_uncertainty_rate": 0.0875,
        "indoor_clean_uncertainty_rate": 0.0083,
        "abstention_rate": 0.0000,
        "per_class": {
            "BIOMASS_OR_WASTE_BURNING": {"precision": 0.915, "recall": 0.617, "f1-score": 0.737},
            "CLEAN_OR_BACKGROUND": {"precision": 0.570, "recall": 1.000, "f1-score": 0.726},
            "CONSTRUCTION_ACTIVITY": {"precision": 0.854, "recall": 0.825, "f1-score": 0.839},
            "COOKING_OR_FUEL_COMBUSTION": {"precision": 0.476, "recall": 0.608, "f1-score": 0.534},
            "HEAVY_DUST": {"precision": 0.934, "recall": 0.933, "f1-score": 0.933},
            "INDOOR_ACTIVITY": {"precision": 0.710, "recall": 0.308, "f1-score": 0.429},
            "INDUSTRIAL_OR_GENERATOR_EMISSIONS": {"precision": 0.537, "recall": 0.225, "f1-score": 0.315},
            "TRAFFIC": {"precision": 0.347, "recall": 0.517, "f1-score": 0.414},
        },
    }
    baseline = TRUE_BASELINE

    # Evaluate candidate across 3 seeds
    candidate_results = []
    seeds = [42, 101, 777]
    for seed in seeds:
        ds = generate_independent_scenarios(seed=seed)
        r = run_evaluation(sc, ds)
        r["seed"] = seed
        candidate_results.append(r)
        print(f"Seed {seed}: Acc={r['accuracy']:.4f}, Macro-F1={r['macro_f1']:.4f}, MixedDet={r['mixture_detection_overall']:.4f}, TrafIndUnc={r['traffic_ind_uncertainty_rate']:.4f}, IndoorCleanUnc={r['indoor_clean_uncertainty_rate']:.4f}")

    mean_acc = float(np.mean([r["accuracy"] for r in candidate_results]))
    mean_f1 = float(np.mean([r["macro_f1"] for r in candidate_results]))
    mean_mix = float(np.mean([r["mixture_detection_overall"] for r in candidate_results]))
    mean_traf_unc = float(np.mean([r["traffic_ind_uncertainty_rate"] for r in candidate_results]))
    mean_indoor_unc = float(np.mean([r["indoor_clean_uncertainty_rate"] for r in candidate_results]))
    mean_abstain = float(np.mean([r["abstention_rate"] for r in candidate_results]))
    mean_conf_amb = float(np.mean([r["mean_conf_ambiguous"] for r in candidate_results]))
    mean_conf_unamb = float(np.mean([r["mean_conf_unambiguous"] for r in candidate_results]))

    # Average per-class candidate metrics
    per_class_candidate = {}
    for cls in SOURCE_CLASSES:
        prec = float(np.mean([r["per_class"][cls]["precision"] for r in candidate_results]))
        rec = float(np.mean([r["per_class"][cls]["recall"] for r in candidate_results]))
        f1 = float(np.mean([r["per_class"][cls]["f1-score"] for r in candidate_results]))
        per_class_candidate[cls] = {"precision": prec, "recall": rec, "f1-score": f1}

    # Sum confusion matrix
    cm_sum = np.sum([np.array(r["confusion_matrix"]) for r in candidate_results], axis=0).tolist()

    report_payload = {
        "metadata": {
            "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
            "seeds": seeds,
            "samples_per_seed": 400,
            "total_samples": 1200,
            "note": "ALL EVALUATION DATA IS SYNTHETIC (generated with independent scenario generator, voltage drift, sensor noise, PM scaling variation)",
        },
        "aggregate_metrics": {
            "baseline": {
                "mean_accuracy": baseline.get("mean_accuracy", 0.6292),
                "mean_macro_f1": baseline.get("mean_macro_f1", 0.6160),
                "mixture_detection_rate": baseline.get("mean_mixed_detection", 0.0),
                "traffic_ind_uncertainty_rate": baseline.get("mean_traffic_ind_uncertainty", 0.0875),
                "indoor_clean_uncertainty_rate": baseline.get("mean_indoor_clean_uncertainty", 0.0083),
                "abstention_rate": 0.0,
            },
            "candidate": {
                "mean_accuracy": mean_acc,
                "mean_macro_f1": mean_f1,
                "mixture_detection_rate": mean_mix,
                "traffic_ind_uncertainty_rate": mean_traf_unc,
                "indoor_clean_uncertainty_rate": mean_indoor_unc,
                "abstention_rate": mean_abstain,
                "calibration": {
                    "mean_confidence_ambiguous_cases": mean_conf_amb,
                    "mean_confidence_unambiguous_cases": mean_conf_unamb,
                },
            },
        },
        "per_class": {
            "baseline": baseline.get("per_class", {}),
            "candidate": per_class_candidate,
        },
        "mixture_breakdown_candidate": {
            k: float(np.mean([r["mixture_breakdown"][k] for r in candidate_results]))
            for k in ["traffic_plus_construction", "combustion_plus_traffic", "industrial_plus_pm", "tri_source_mixture"]
        },
        "candidate_confusion_matrix_sum": cm_sum,
        "classes": SOURCE_CLASSES,
    }

    out_file = Path("scratch/phase2b_evaluation_report.json")
    with open(out_file, "w") as f:
        json.dump(report_payload, f, indent=2)

    print("\n=======================================================")
    print("PHASE 2B SOURCE CLASSIFIER EVALUATION REPORT")
    print("=======================================================")
    print(f"Mean Accuracy           : Baseline={report_payload['aggregate_metrics']['baseline']['mean_accuracy']:.4f} -> Candidate={mean_acc:.4f}")
    print(f"Mean Macro-F1           : Baseline={report_payload['aggregate_metrics']['baseline']['mean_macro_f1']:.4f} -> Candidate={mean_f1:.4f}")
    print(f"Mixture Detection Rate  : Baseline={report_payload['aggregate_metrics']['baseline']['mixture_detection_rate']:.4f} -> Candidate={mean_mix:.4f}")
    print(f"Traffic/Ind Uncertainty : Baseline={report_payload['aggregate_metrics']['baseline']['traffic_ind_uncertainty_rate']:.4f} -> Candidate={mean_traf_unc:.4f}")
    print(f"Indoor/Clean Uncertainty: Baseline={report_payload['aggregate_metrics']['baseline']['indoor_clean_uncertainty_rate']:.4f} -> Candidate={mean_indoor_unc:.4f}")
    print(f"Abstention Rate         : Candidate={mean_abstain:.4f}")
    print(f"Confidence Calibration  : Ambiguous={mean_conf_amb:.4f} vs Unambiguous={mean_conf_unamb:.4f}")
    print("\nMixture Breakdown (Candidate):")
    for k, v in report_payload["mixture_breakdown_candidate"].items():
        print(f"  {k:30s}: {v*100.0:.1f}%")
    print("\nPer-Class Comparison (Baseline vs Candidate):")
    print(f"{'Class':35s} | {'Base P':6s} {'Base R':6s} {'Base F1':7s} | {'Cand P':6s} {'Cand R':6s} {'Cand F1':7s}")
    print("-" * 80)
    for cls in SOURCE_CLASSES:
        bp = baseline.get("per_class", {}).get(cls, {}).get("precision", 0.0)
        br = baseline.get("per_class", {}).get(cls, {}).get("recall", 0.0)
        bf = baseline.get("per_class", {}).get(cls, {}).get("f1-score", 0.0)
        cp = per_class_candidate[cls]["precision"]
        cr = per_class_candidate[cls]["recall"]
        cf = per_class_candidate[cls]["f1-score"]
        print(f"{cls:35s} | {bp:.3f}  {br:.3f}  {bf:.3f}   | {cp:.3f}  {cr:.3f}  {cf:.3f}")
    print("=======================================================\n")
