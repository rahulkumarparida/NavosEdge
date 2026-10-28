"""
NavosEdge Model Audit and Baseline Evaluation Script.
Evaluates current runtime model artifacts:
1. TinyGasNet (NumpyGasNetAdapter)
2. SourceClassifier
3. Forecasting (AR vs Persistence)
4. Anomaly Engine
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

# Add project root and Intelligence/Server to path
root_dir = Path(__file__).resolve().parents[1]
server_dir = root_dir / "Intelligence" / "Server"
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

import numpy as np
from app.services.numpy_inference import NumpyGasNetAdapter
from app.source_classifier.classifier import SourceClassifier
from app.source_classifier.categories import SourceCategory, SourceClassifierConfig
from app.schemas.sensor import SensorPayload
from app.forecast.model import _fit_ar, _ar_predict
from app.anomaly.engine import AnomalyEngine
from Simulator.session import load_dataset


def evaluate_gasnet_baseline(artifacts_dir: Path):
    print("=" * 60)
    print("1. EVALUATING CURRENT TINYGASNET BASELINE")
    print("=" * 60)

    adapter = NumpyGasNetAdapter(artifacts_dir=artifacts_dir)
    adapter.load()
    print(f"TinyGasNet loaded: {adapter._loaded}")
    if not adapter._loaded:
        return {"loaded": False}

    metadata_path = artifacts_dir / "model_metadata.json"
    with open(metadata_path) as f:
        meta = json.load(f)

    print(f"Model version: {meta.get('model_version')}")
    print(f"Classes: {meta.get('class_labels')}")
    print(f"Scaler mean: {meta.get('preprocessing', {}).get('scaler_mean')}")
    print(f"Scaler scale: {meta.get('preprocessing', {}).get('scaler_scale')}")

    # Test cases:
    # A: Clean Indoor / Clean Air at nominal training temp (30C, 87% hum)
    # B: Clean Indoor at normal room temp (25C, 50% hum)
    # C: Smoke scenario at normal room temp (25C, 50% hum)
    # D: Alcohol scenario
    test_cases = [
        {"name": "Clean Air (Nominal 30C, 87%H)", "mq2": 0.80, "mq9": 0.70, "mq135": 0.75, "t": 30.15, "h": 87.05, "expected": "CleanAir"},
        {"name": "Clean Air (Real-world 25C, 50%H)", "mq2": 0.80, "mq9": 0.70, "mq135": 0.75, "t": 25.0, "h": 50.0, "expected": "CleanAir"},
        {"name": "Clean Air (Cool 20C, 60%H)", "mq2": 0.75, "mq9": 0.65, "mq135": 0.70, "t": 20.0, "h": 60.0, "expected": "CleanAir"},
        {"name": "Smoke Event (Elevated MQ2, 25C, 50%H)", "mq2": 2.65, "mq9": 1.75, "mq135": 2.25, "t": 25.0, "h": 50.0, "expected": "Smoke"},
        {"name": "Alcohol Event (Elevated MQ135, 25C, 50%H)", "mq2": 0.95, "mq9": 0.85, "mq135": 2.75, "t": 25.0, "h": 50.0, "expected": "Alcohol"},
        {"name": "CO Event (Elevated MQ9, 25C, 50%H)", "mq2": 1.15, "mq9": 2.60, "mq135": 1.30, "t": 25.0, "h": 50.0, "expected": "CO"},
        {"name": "LPG Event (Elevated MQ2 & MQ9, 25C, 50%H)", "mq2": 2.40, "mq9": 2.10, "mq135": 1.20, "t": 25.0, "h": 50.0, "expected": "LPG"},
    ]

    import asyncio
    results = []
    for tc in test_cases:
        res = asyncio.run(adapter.predict(tc["mq2"], tc["mq9"], tc["mq135"], tc["t"], tc["h"]))
        results.append({
            "name": tc["name"],
            "expected": tc["expected"],
            "predicted": res.gas_class,
            "confidence": res.class_confidence,
            "safety": res.safety_status,
            "uncertainty": res.uncertainty,
            "features_scaled_t": (tc["t"] - meta['preprocessing']['scaler_mean'][3]) / meta['preprocessing']['scaler_scale'][3],
            "features_scaled_h": (tc["h"] - meta['preprocessing']['scaler_mean'][4]) / meta['preprocessing']['scaler_scale'][4],
        })
        print(f"Test '{tc['name']}': Expected={tc['expected']} -> Predicted={res.gas_class} (conf={res.class_confidence:.3f}, safety={res.safety_status}, uncertainty={res.uncertainty:.3f})")
        print(f"   Scaled T z-score: {results[-1]['features_scaled_t']:.1f} std, Scaled H z-score: {results[-1]['features_scaled_h']:.1f} std")

    return {"meta": meta, "results": results}


def evaluate_source_classifier_baseline(artifacts_dir: Path):
    print("\n" + "=" * 60)
    print("2. EVALUATING CURRENT SOURCE CLASSIFIER BASELINE")
    print("=" * 60)

    classifier = SourceClassifier(artifacts_dir=artifacts_dir)
    loaded = classifier.load()
    print(f"SourceClassifier loaded: {loaded}")
    metadata_path = artifacts_dir / "source_classifier_metadata.json"
    with open(metadata_path) as f:
        meta = json.load(f)
    print(f"Reported metadata accuracy: {meta.get('evaluation', {}).get('accuracy')}")
    print(f"Classes: {meta.get('classes')}")

    # Build representative payloads for distinct environmental scenarios
    test_scenarios = [
        ("CLEAN_OR_BACKGROUND", {
            "node_id": "test-node", "timestamp": "2024-09-01T10:00:00Z",
            "environment": {"temperature_C": 27.0, "humidity_pct": 55.0},
            "particulate_matter": {"PM1_0": 6.0, "PM2_5": 12.0, "PM10": 20.0},
            "gas_sensors": {"MQ2": {"raw_adc": 140, "voltage_V": 0.70}, "MQ9": {"raw_adc": 130, "voltage_V": 0.65}, "MQ135": {"raw_adc": 160, "voltage_V": 0.80}}
        }),
        ("TRAFFIC", {
            "node_id": "test-node", "timestamp": "2024-09-01T10:00:00Z",
            "environment": {"temperature_C": 31.0, "humidity_pct": 50.0},
            "particulate_matter": {"PM1_0": 25.0, "PM2_5": 65.0, "PM10": 110.0},
            "gas_sensors": {"MQ2": {"raw_adc": 320, "voltage_V": 1.60}, "MQ9": {"raw_adc": 380, "voltage_V": 1.90}, "MQ135": {"raw_adc": 340, "voltage_V": 1.70}}
        }),
        ("CONSTRUCTION_ACTIVITY", {
            "node_id": "test-node", "timestamp": "2024-09-01T10:00:00Z",
            "environment": {"temperature_C": 34.0, "humidity_pct": 40.0},
            "particulate_matter": {"PM1_0": 20.0, "PM2_5": 60.0, "PM10": 260.0},
            "gas_sensors": {"MQ2": {"raw_adc": 220, "voltage_V": 1.10}, "MQ9": {"raw_adc": 265, "voltage_V": 1.30}, "MQ135": {"raw_adc": 245, "voltage_V": 1.20}}
        }),
        ("BIOMASS_OR_WASTE_BURNING", {
            "node_id": "test-node", "timestamp": "2024-09-01T10:00:00Z",
            "environment": {"temperature_C": 32.0, "humidity_pct": 50.0},
            "particulate_matter": {"PM1_0": 65.0, "PM2_5": 130.0, "PM10": 160.0},
            "gas_sensors": {"MQ2": {"raw_adc": 580, "voltage_V": 2.85}, "MQ9": {"raw_adc": 410, "voltage_V": 2.00}, "MQ135": {"raw_adc": 510, "voltage_V": 2.50}}
        }),
        ("HEAVY_DUST", {
            "node_id": "test-node", "timestamp": "2024-09-01T10:00:00Z",
            "environment": {"temperature_C": 36.0, "humidity_pct": 35.0},
            "particulate_matter": {"PM1_0": 20.0, "PM2_5": 60.0, "PM10": 420.0},
            "gas_sensors": {"MQ2": {"raw_adc": 170, "voltage_V": 0.85}, "MQ9": {"raw_adc": 160, "voltage_V": 0.80}, "MQ135": {"raw_adc": 180, "voltage_V": 0.90}}
        }),
    ]

    sc_results = []
    correct = 0
    for expected_src, payload_dict in test_scenarios:
        payload = SensorPayload.model_validate(payload_dict)
        res = classifier.classify(payload)
        pred_src = res.get("top_source") or "UNKNOWN"
        top_pred = res["predictions"][0] if res.get("predictions") else {"match_score": 0.0}
        match_score = top_pred.get("match_score", 0.0)
        is_match = (expected_src == pred_src) or (expected_src in pred_src)
        if is_match:
            correct += 1
        sc_results.append({
            "expected": expected_src,
            "predicted": pred_src,
            "match_score": match_score,
            "uncertainty": res.get("uncertainty", {}).get("is_uncertain"),
            "correct": is_match,
        })
        print(f"Scenario '{expected_src}': Predicted={pred_src} (score={match_score:.3f}, uncertain={res.get('uncertainty', {}).get('is_uncertain')}) -> {'PASS' if is_match else 'FAIL'}")

    acc = correct / len(test_scenarios)
    print(f"Accuracy on canonical scenarios: {correct}/{len(test_scenarios)} ({acc*100:.1f}%)")
    return {"meta": meta, "results": sc_results, "accuracy": acc}


def evaluate_forecast_baseline():
    print("\n" + "=" * 60)
    print("3. EVALUATING FORECASTING BASELINE (35-DAY DATASET)")
    print("=" * 60)

    dataset_path = Path("test_data/historical_35d.jsonl")
    if not dataset_path.exists():
        print(f"Historical dataset not found at {dataset_path}")
        return {}

    records = load_dataset(dataset_path)
    pm25_series = [r["particulate_matter"]["PM2_5"] for r in records if "particulate_matter" in r]
    pm10_series = [r["particulate_matter"]["PM10"] for r in records if "particulate_matter" in r]

    # Chronological 80/20 train/test split
    split_idx = int(len(pm25_series) * 0.8)
    results = {}

    for horizon_name, horizon_steps in [("15m (3 steps)", 3), ("30m (6 steps)", 6), ("60m (12 steps)", 12)]:
        def eval_channel(series):
            train = series[:split_idx]
            test = series[split_idx:]
            coeffs, intercept = _fit_ar(train, order=3)

            p_preds, ar_preds, actuals = [], [], []
            for step in range(len(test) - horizon_steps):
                hist = list(train) + list(test[:step])
                p_preds.append(hist[-1])
                ar_pred_seq = _ar_predict(coeffs, intercept, hist, horizon_steps)
                ar_preds.append(ar_pred_seq[-1])
                actuals.append(test[step + horizon_steps])

            p_mae = sum(abs(p - a) for p, a in zip(p_preds, actuals)) / len(actuals)
            p_rmse = math.sqrt(sum((p - a)**2 for p, a in zip(p_preds, actuals)) / len(actuals))
            ar_mae = sum(abs(p - a) for p, a in zip(ar_preds, actuals)) / len(actuals)
            ar_rmse = math.sqrt(sum((p - a)**2 for p, a in zip(ar_preds, actuals)) / len(actuals))
            return {
                "persistence_mae": p_mae, "persistence_rmse": p_rmse,
                "ar_mae": ar_mae, "ar_rmse": ar_rmse, "eval_count": len(actuals)
            }

        res_pm25 = eval_channel(pm25_series)
        res_pm10 = eval_channel(pm10_series)
        results[horizon_name] = {"PM2.5": res_pm25, "PM10": res_pm10}

        print(f"Horizon {horizon_name}:")
        print(f"  PM2.5 -> Persistence MAE: {res_pm25['persistence_mae']:.2f}, RMSE: {res_pm25['persistence_rmse']:.2f} | AR MAE: {res_pm25['ar_mae']:.2f}, RMSE: {res_pm25['ar_rmse']:.2f}")
        print(f"  PM10  -> Persistence MAE: {res_pm10['persistence_mae']:.2f}, RMSE: {res_pm10['persistence_rmse']:.2f} | AR MAE: {res_pm10['ar_mae']:.2f}, RMSE: {res_pm10['ar_rmse']:.2f}")

    return results


def main():
    artifacts_dir = server_dir / "artifacts"
    gasnet_res = evaluate_gasnet_baseline(artifacts_dir)
    sc_res = evaluate_source_classifier_baseline(artifacts_dir)
    fc_res = evaluate_forecast_baseline()

    baseline_data = {
        "tinygasnet": gasnet_res,
        "source_classifier": sc_res,
        "forecasting": fc_res,
    }
    out_file = Path("test_data/model_evaluation_baseline.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(baseline_data, f, indent=2, default=str)
    print(f"\nSaved full baseline evaluation to {out_file}")


if __name__ == "__main__":
    main()
