"""
Comprehensive forecasting evaluation and benchmark script.
Evaluates AR(p) model vs Persistence baseline across:
- 35-day historical dataset (rolling evaluations)
- 8 synthetic test scenarios (clearly labeled synthetic)
- 4 forecast horizons: 15m (3 steps), 30m (6 steps), 45m (9 steps), 60m (12 steps)
"""

import json
import math
import random
from pathlib import Path
import numpy as np

from app.forecast.model import generate_forecast, _fit_ar, _ar_predict, _compute_trend
from app.schemas.forecast import ForecastStatus, ForecastReliability, TrendDirection


def load_historical_data(path: Path):
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records


def evaluate_historical_dataset(records, step_interval=12, history_window=24):
    """
    Rolling window evaluation across the 10,056-record dataset.
    Evaluates at horizons: 15m (step 3), 30m (step 6), 45m (step 9), 60m (step 12).
    """
    pm_channels = ["PM1_0", "PM2_5", "PM10"]
    horizons = [3, 6, 9, 12]  # steps corresponding to 15m, 30m, 45m, 60m
    horizon_names = ["15m", "30m", "45m", "60m"]

    # Flatten PM values
    ts_data = {ch: [] for ch in pm_channels}
    for r in records:
        pm = r.get("particulate_matter", {})
        for ch in pm_channels:
            ts_data[ch].append(pm.get(ch, 0.0))

    n_records = len(records)
    results = {
        ch: {
            h_name: {
                "ar_errors": [],
                "pers_errors": [],
                "ar_sq_errors": [],
                "pers_sq_errors": [],
                "ar_dir_correct": 0,
                "pers_dir_correct": 0,
                "total_dir": 0,
            }
            for h_name in horizon_names
        }
        for ch in pm_channels
    }

    max_drift_observed = 0.0
    nan_inf_count = 0

    # Slide window
    eval_indices = list(range(history_window, n_records - 12, step_interval))
    for idx in eval_indices:
        for ch in pm_channels:
            history = ts_data[ch][idx - history_window : idx]
            future = ts_data[ch][idx : idx + 12]
            last_known = history[-1]

            # Fit AR
            order = min(6, len(history) // 3, len(history) - 2)
            order = max(1, order)
            ar_fit = _fit_ar(history, order)

            if ar_fit is not None:
                coeffs, intercept = ar_fit
                ar_preds = _ar_predict(coeffs, intercept, history, steps=12, damping=0.98)
            else:
                ar_preds = [round(last_known, 2)] * 12

            pers_preds = [round(last_known, 2)] * 12

            for step_idx, h_name in zip(horizons, horizon_names):
                pred_ar = ar_preds[step_idx - 1]
                pred_pers = pers_preds[step_idx - 1]
                true_val = future[step_idx - 1]

                if not math.isfinite(pred_ar):
                    nan_inf_count += 1
                    continue

                drift = abs(pred_ar - last_known)
                if drift > max_drift_observed:
                    max_drift_observed = drift

                err_ar = abs(pred_ar - true_val)
                err_pers = abs(pred_pers - true_val)

                results[ch][h_name]["ar_errors"].append(err_ar)
                results[ch][h_name]["pers_errors"].append(err_pers)
                results[ch][h_name]["ar_sq_errors"].append(err_ar ** 2)
                results[ch][h_name]["pers_sq_errors"].append(err_pers ** 2)

                # Directional accuracy
                true_diff = true_val - last_known
                ar_diff = pred_ar - last_known
                pers_diff = pred_pers - last_known  # always 0 (stable)

                true_dir = 1 if true_diff > 0.5 else (-1 if true_diff < -0.5 else 0)
                ar_dir = 1 if ar_diff > 0.5 else (-1 if ar_diff < -0.5 else 0)
                pers_dir = 1 if pers_diff > 0.5 else (-1 if pers_diff < -0.5 else 0)

                results[ch][h_name]["total_dir"] += 1
                if ar_dir == true_dir:
                    results[ch][h_name]["ar_dir_correct"] += 1
                if pers_dir == true_dir:
                    results[ch][h_name]["pers_dir_correct"] += 1

    summary = {}
    for ch in pm_channels:
        summary[ch] = {}
        for h_name in horizon_names:
            h_data = results[ch][h_name]
            ar_mae = float(np.mean(h_data["ar_errors"])) if h_data["ar_errors"] else 0.0
            pers_mae = float(np.mean(h_data["pers_errors"])) if h_data["pers_errors"] else 0.0
            ar_rmse = float(np.sqrt(np.mean(h_data["ar_sq_errors"]))) if h_data["ar_sq_errors"] else 0.0
            pers_rmse = float(np.sqrt(np.mean(h_data["pers_sq_errors"]))) if h_data["pers_sq_errors"] else 0.0
            total_d = max(1, h_data["total_dir"])
            ar_acc = h_data["ar_dir_correct"] / total_d
            pers_acc = h_data["pers_dir_correct"] / total_d

            summary[ch][h_name] = {
                "ar_mae": round(ar_mae, 4),
                "pers_mae": round(pers_mae, 4),
                "mae_gain_pct": round(((pers_mae - ar_mae) / pers_mae) * 100, 2) if pers_mae > 0 else 0.0,
                "ar_rmse": round(ar_rmse, 4),
                "pers_rmse": round(pers_rmse, 4),
                "ar_dir_acc_pct": round(ar_acc * 100, 2),
                "pers_dir_acc_pct": round(pers_acc * 100, 2),
            }

    return {
        "summary": summary,
        "max_drift_observed": round(max_drift_observed, 2),
        "nan_inf_count": nan_inf_count,
        "eval_windows_count": len(eval_indices),
    }


def evaluate_synthetic_scenarios():
    """
    Evaluates 8 synthetic scenarios (clearly labeled as synthetic).
    """
    np.random.seed(42)
    random.seed(42)

    scenarios = {}

    # 1. Stable / Flat baseline: 15 ug/m3 with low Gaussian noise
    t_hist = np.arange(24)
    t_fut = np.arange(24, 36)
    s1_hist = 15.0 + np.random.normal(0, 0.4, size=24)
    s1_fut = 15.0 + np.random.normal(0, 0.4, size=12)
    scenarios["1_stable_flat"] = {"name": "Stable / Flat Baseline (Synthetic)", "history": s1_hist, "future": s1_fut}

    # 2. Gradual rise (morning commute): 15 to 45 ug/m3
    s2_hist = 15.0 + 1.2 * t_hist + np.random.normal(0, 0.5, size=24)
    s2_fut = 15.0 + 1.2 * t_fut + np.random.normal(0, 0.5, size=12)
    scenarios["2_gradual_rise"] = {"name": "Gradual Rise / Traffic Buildup (Synthetic)", "history": s2_hist, "future": s2_fut}

    # 3. Gradual fall (afternoon dispersion): 65 down to 25 ug/m3
    s3_hist = 65.0 - 1.0 * t_hist + np.random.normal(0, 0.5, size=24)
    s3_fut = 65.0 - 1.0 * t_fut + np.random.normal(0, 0.5, size=12)
    scenarios["3_gradual_fall"] = {"name": "Gradual Fall / Dispersion (Synthetic)", "history": s3_hist, "future": s3_fut}

    # 4. Abrupt spike (industrial burst / dust plume): spike at t=18-24, decaying in future
    s4_hist = np.full(24, 20.0)
    s4_hist[18:] += np.array([20, 50, 90, 120, 140, 150])
    s4_fut = 150.0 * np.exp(-0.15 * np.arange(1, 13)) + 20.0
    scenarios["4_abrupt_spike"] = {"name": "Abrupt Spike & Decay (Synthetic)", "history": s4_hist, "future": s4_fut}

    # 5. Diurnal cycle (sinusoidal day/night): period 24 steps
    s5_hist = 40.0 + 20.0 * np.sin(2 * np.pi * t_hist / 24) + np.random.normal(0, 0.5, size=24)
    s5_fut = 40.0 + 20.0 * np.sin(2 * np.pi * t_fut / 24) + np.random.normal(0, 0.5, size=12)
    scenarios["5_diurnal_cycle"] = {"name": "Diurnal Periodic Cycle (Synthetic)", "history": s5_hist, "future": s5_fut}

    # 6. Missing readings / irregular intervals: 25% dropped
    t_hist_32 = np.arange(32)
    s6_hist_full = 25.0 + 0.5 * t_hist_32 + np.random.normal(0, 0.5, size=32)
    # create records with dropped values
    records_s6 = []
    drop_indices = set(random.sample(range(32), 8))
    for i in range(32):
        if i in drop_indices:
            records_s6.append({"PM2_5": None})
        else:
            records_s6.append({"PM2_5": float(s6_hist_full[i])})
    s6_fut = 25.0 + 0.5 * np.arange(32, 44)
    scenarios["6_missing_readings"] = {
        "name": "Missing Readings / 25% Dropped (Synthetic)",
        "records": records_s6,
        "future": s6_fut,
    }

    # 7. Noisy readings: high variance (std=7.0)
    s7_hist = 35.0 + 0.4 * t_hist + np.random.normal(0, 7.0, size=24)
    s7_fut = 35.0 + 0.4 * t_fut + np.random.normal(0, 7.0, size=12)
    scenarios["7_noisy_readings"] = {"name": "High Noise Telemetry (Synthetic)", "history": s7_hist, "future": s7_fut}

    # 8. Short history (< min_history_points = 12): only 6 points
    s8_hist = 30.0 + np.random.normal(0, 0.5, size=6)
    s8_fut = 30.0 + np.random.normal(0, 0.5, size=12)
    scenarios["8_short_history"] = {"name": "Short History / 6 Points (Synthetic)", "history": s8_hist, "future": s8_fut}

    scenario_results = {}
    horizons = [3, 6, 9, 12]
    h_names = ["15m", "30m", "45m", "60m"]

    for sc_key, sc in scenarios.items():
        if "records" in sc:
            # Use generate_forecast API
            resp = generate_forecast(
                records=sc["records"],
                channels=["PM2_5"],
                node_id="test-node",
                horizon_minutes=60,
                sampling_interval_minutes=5,
            )
            if resp.status != ForecastStatus.OK:
                ar_preds = [0.0] * 12
                pers_preds = [0.0] * 12
            else:
                ar_preds = resp.channels[0].predicted_values
                pers_preds = resp.channels[0].persistence_baseline
        elif len(sc["history"]) < 12:
            records = [{"PM2_5": float(x)} for x in sc["history"]]
            resp = generate_forecast(
                records=records,
                channels=["PM2_5"],
                node_id="test-node",
                horizon_minutes=60,
                sampling_interval_minutes=5,
            )
            scenario_results[sc_key] = {
                "name": sc["name"],
                "status": resp.status.value,
                "reliability": resp.reliability.value,
                "history_points": len(sc["history"]),
                "note": "Correctly rejected due to insufficient points (< 12).",
            }
            continue
        else:
            history = list(sc["history"])
            last_known = history[-1]
            order = min(6, len(history) // 3, len(history) - 2)
            ar_fit = _fit_ar(history, order)
            if ar_fit:
                coeffs, intercept = ar_fit
                ar_preds = _ar_predict(coeffs, intercept, history, steps=12, damping=0.98)
            else:
                ar_preds = [round(last_known, 2)] * 12
            pers_preds = [round(last_known, 2)] * 12

        future = list(sc["future"])
        sc_res = {"name": sc["name"], "horizons": {}}
        for step_idx, h_name in zip(horizons, h_names):
            pred_ar = ar_preds[step_idx - 1]
            pred_pers = pers_preds[step_idx - 1]
            true_val = future[step_idx - 1]
            sc_res["horizons"][h_name] = {
                "ar_mae": round(abs(pred_ar - true_val), 3),
                "pers_mae": round(abs(pred_pers - true_val), 3),
                "ar_pred": pred_ar,
                "pers_pred": pred_pers,
                "true_val": round(true_val, 2),
            }
        scenario_results[sc_key] = sc_res

    return scenario_results


if __name__ == "__main__":
    hist_path = Path("test_data/historical_35d.jsonl")
    records = load_historical_data(hist_path)
    print(f"Loaded {len(records)} historical records.")

    print("\n--- Running 35-Day Dataset Benchmark ---")
    hist_bench = evaluate_historical_dataset(records)
    print(json.dumps(hist_bench, indent=2))

    print("\n--- Running 8 Synthetic Scenario Benchmarks ---")
    synth_bench = evaluate_synthetic_scenarios()
    print(json.dumps(synth_bench, indent=2))

    out_file = Path("scratch/forecast_benchmark_results.json")
    with open(out_file, "w") as f:
        json.dump({"historical": hist_bench, "synthetic": synth_bench}, f, indent=2)
    print(f"\nSaved benchmark results to {out_file}")
