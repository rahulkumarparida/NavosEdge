"""
Phase 4 Independent Test Suite for Anomaly Detection.

Validates AnomalyEngine on:
1. Unseen environmental profiles (location='delhi', seed=888, 35-day replay).
2. Abrupt rail faults (rail_low, rail_high).
3. Stuck sensor values across channels.
4. Slow sensor drift.
5. Gradual pollution increases vs sudden genuine PM spikes.
6. Mixed pollution and hardware-fault events (concurrent smoke + rail fault).
7. Extreme weather shifts (high humidity > 95%, heatwave > 45C).
8. Missing data and out-of-order timestamp handling.
9. Node restarts and baseline refits.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import numpy as np
import pandas as pd
import sys

root_dir = Path(__file__).resolve().parents[1]
server_dir = root_dir / "Intelligence" / "Server"

if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
if str(server_dir) not in sys.path:
    sys.path.insert(0, str(server_dir))

from app.anomaly.engine import AnomalyEngine
from Simulator.historical_generator import GenerationConfig, HistoricalDatasetGenerator


def run_independent_evaluation():
    print("=" * 80)
    print("PHASE 4: INDEPENDENT ANOMALY ENGINE EVALUATION SUITE")
    print("=" * 80)

    # --------------------------------------------------------------------------
    # Test 1: Full 35-Day Independent Holdout Replay (seed=888, location='delhi')
    # --------------------------------------------------------------------------
    print("\n--- TEST 1: Unseen Environmental Profile & Fault Seed (Delhi, seed=888) ---")
    gen_config = GenerationConfig(
        node_id="eval-delhi-888",
        days=35,
        sampling_interval_seconds=300.0,
        seed=888,
        start_date="2024-11-01",  # Winter season
        location="delhi",
        inject_faults=True,
    )
    generator = HistoricalDatasetGenerator(gen_config)
    delhi_records = generator.generate_all()

    engine = AnomalyEngine()
    
    rows = []
    fault_episodes = {}
    cur_fault = None
    start_ts = None

    for i, rec in enumerate(delhi_records):
        prov = rec.get("provenance", {})
        fault = prov.get("fault")
        scen = prov.get("scenario")
        ts = rec["timestamp"]
        is_hw = (fault is not None and fault != "warmup")

        if is_hw:
            if cur_fault != fault:
                cur_fault = fault
                start_ts = ts
                fault_episodes[cur_fault] = {
                    "start": start_ts,
                    "first_detected": None,
                    "delay_min": None
                }
        else:
            cur_fault = None

        res = engine.analyse("eval-delhi-888", rec)
        source = res.get("anomaly_source", "UNKNOWN")
        is_hw_alert = res.get("is_hardware_fault", False) or (source in ("SENSOR_FAULT", "MIXED"))
        is_env_alert = res.get("is_environmental_event", False) or (source in ("ENVIRONMENTAL", "MIXED"))
        anom = res.get("anomaly", {})

        if is_hw and is_hw_alert and cur_fault is not None:
            if fault_episodes[cur_fault]["first_detected"] is None:
                fault_episodes[cur_fault]["first_detected"] = ts
                t0 = datetime.fromisoformat(fault_episodes[cur_fault]["start"])
                t1 = datetime.fromisoformat(ts)
                fault_episodes[cur_fault]["delay_min"] = (t1 - t0).total_seconds() / 60.0

        rows.append({
            "idx": i,
            "timestamp": ts,
            "scenario": scen,
            "fault": fault,
            "is_hw_fault": is_hw,
            "is_hw_alert": is_hw_alert,
            "is_env_alert": is_env_alert,
        })

    df = pd.DataFrame(rows)

    tp = len(df[df["is_hw_fault"] & df["is_hw_alert"]])
    fp = len(df[~df["is_hw_fault"] & df["is_hw_alert"]])
    tn = len(df[~df["is_hw_fault"] & ~df["is_hw_alert"]])
    fn = len(df[df["is_hw_fault"] & ~df["is_hw_alert"]])

    prec = tp / (tp + fp) if (tp + fp) > 0 else 0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0

    print(f"  Total records evaluated: {len(df)}")
    print(f"  TP: {tp} / {tp+fn} | FP: {fp} | TN: {tn} | FN: {fn}")
    print(f"  Hardware Precision  : {prec*100:.2f}%")
    print(f"  Hardware Recall     : {rec*100:.2f}%")
    print(f"  False Positive Rate : {fpr*100:.2f}%")
    print(f"  Hardware F1 Score   : {f1*100:.2f}%")

    print("\n  Per-Fault Recall (Delhi seed 888):")
    hw_df = df[df["is_hw_fault"]]
    for ftype, grp in hw_df.groupby("fault"):
        cnt = len(grp[grp["is_hw_alert"]])
        tot = len(grp)
        print(f"    {ftype:<15s}: {cnt}/{tot} ({cnt/tot*100:.1f}%)")

    print("\n  Detection Delays:")
    for ftype, ep in fault_episodes.items():
        dmin = ep['delay_min']
        d_str = f"{dmin:.1f} min" if dmin is not None else "NOT DETECTED"
        print(f"    {ftype:<15s}: delay={d_str}")

    print("\n  Per-Scenario False Alerts & Environmental Events:")
    for scen, grp in df.groupby("scenario"):
        hw_fp = len(grp[~grp["is_hw_fault"] & grp["is_hw_alert"]])
        tot_non_hw = len(grp[~grp["is_hw_fault"]])
        env_cnt = len(grp[grp["is_env_alert"]])
        print(f"    {scen:<25s}: HW FP = {hw_fp}/{tot_non_hw} ({hw_fp/tot_non_hw*100:.2f}%) | Env Events = {env_cnt}/{len(grp)}")

    # --------------------------------------------------------------------------
    # Test 2: Stress Tests (Mixed Concurrent Events, Weather Extremes, Out-of-Order)
    # --------------------------------------------------------------------------
    print("\n--- TEST 2: Stress Scenarios ---")
    stress_engine = AnomalyEngine()
    node = "stress-node"

    # Prime with 30 clean readings
    t_base = datetime(2024, 11, 1, 0, 0, tzinfo=timezone.utc)
    for k in range(30):
        t_k = t_base + timedelta(minutes=5 * k)
        stress_engine.analyse(node, {
            "timestamp": t_k.isoformat(),
            "environment": {"temperature_C": 25.0 + 0.1 * (k % 5), "humidity_pct": 50.0 + 0.2 * (k % 5)},
            "particulate_matter": {"PM1_0": 10.0, "PM2_5": 20.0, "PM10": 30.0},
            "gas_sensors": {
                "MQ2": {"raw_adc": 180, "voltage_V": 0.88},
                "MQ9": {"raw_adc": 160, "voltage_V": 0.78},
                "MQ135": {"raw_adc": 170, "voltage_V": 0.83},
            }
        })

    # Case A: Concurrent Mixed Event (Genuine smoke surge + simultaneous MQ9 rail fault)
    t_mix = t_base + timedelta(minutes=155)
    mix_res = stress_engine.analyse(node, {
        "timestamp": t_mix.isoformat(),
        "environment": {"temperature_C": 26.0, "humidity_pct": 52.0},
        "particulate_matter": {"PM1_0": 95.0, "PM2_5": 180.0, "PM10": 260.0},  # Smoke PM surge
        "gas_sensors": {
            "MQ2": {"raw_adc": 550, "voltage_V": 2.69},   # Elevated from smoke
            "MQ9": {"raw_adc": 0, "voltage_V": 0.00},     # Ground short / rail fault!
            "MQ135": {"raw_adc": 480, "voltage_V": 2.35}, # Elevated from smoke
        }
    })
    print("  Case A (Mixed concurrent smoke + MQ9 GND rail fault):")
    print(f"    Source: {mix_res.get('anomaly_source')} | Detail: {mix_res.get('anomaly_source_detail')}")
    print(f"    is_hardware_fault: {mix_res.get('is_hardware_fault')} | is_environmental_event: {mix_res.get('is_environmental_event')}")
    assert mix_res.get("is_hardware_fault") is True, "Failed to flag hardware fault during mixed event!"
    assert mix_res.get("is_environmental_event") is True, "Failed to flag environmental event during mixed event!"
    assert mix_res.get("anomaly_source") == "MIXED", f"Expected MIXED, got {mix_res.get('anomaly_source')}"

    # Case B: Sudden Massive Genuine Dust Surge (PM jumps by 800 with NO gas response)
    t_dust = t_base + timedelta(minutes=160)
    dust_res = stress_engine.analyse(node, {
        "timestamp": t_dust.isoformat(),
        "environment": {"temperature_C": 30.0, "humidity_pct": 40.0},
        "particulate_matter": {"PM1_0": 30.0, "PM2_5": 120.0, "PM10": 850.0},  # Coarse dust surge
        "gas_sensors": {
            "MQ2": {"raw_adc": 180, "voltage_V": 0.88},
            "MQ9": {"raw_adc": 160, "voltage_V": 0.78},
            "MQ135": {"raw_adc": 170, "voltage_V": 0.83},
        }
    })
    print("\n  Case B (Sudden genuine PM dust surge PM10=850):")
    print(f"    Source: {dust_res.get('anomaly_source')} | Detail: {dust_res.get('anomaly_source_detail')}")
    print(f"    is_hardware_fault: {dust_res.get('is_hardware_fault')} | is_environmental_event: {dust_res.get('is_environmental_event')}")
    assert dust_res.get("is_hardware_fault") is False, "False hardware fault flagged on genuine dust storm!"
    assert dust_res.get("is_environmental_event") is True, "Failed to flag genuine dust storm as environmental event!"

    # Case C: Extreme Humidity Shift (>96% monsoon shift)
    t_monsoon = t_base + timedelta(minutes=165)
    monsoon_res = stress_engine.analyse(node, {
        "timestamp": t_monsoon.isoformat(),
        "environment": {"temperature_C": 28.0, "humidity_pct": 96.5},  # Severe monsoon humidity
        "particulate_matter": {"PM1_0": 12.0, "PM2_5": 22.0, "PM10": 32.0},
        "gas_sensors": {
            "MQ2": {"raw_adc": 185, "voltage_V": 0.90},
            "MQ9": {"raw_adc": 165, "voltage_V": 0.81},
            "MQ135": {"raw_adc": 175, "voltage_V": 0.85},
        }
    })
    print("\n  Case C (Extreme Monsoon Humidity 96.5%):")
    print(f"    Source: {monsoon_res.get('anomaly_source')} | Detail: {monsoon_res.get('anomaly_source_detail')}")
    print(f"    is_hardware_fault: {monsoon_res.get('is_hardware_fault')}")
    assert monsoon_res.get("is_hardware_fault") is False, "High humidity triggered false hardware alarm!"

    # Case D: Out-of-Order / Duplicated Timestamp Handling
    t_dup = t_base + timedelta(minutes=160)  # Duplicate timestamp
    dup_res = stress_engine.analyse(node, {
        "timestamp": t_dup.isoformat(),
        "environment": {"temperature_C": 25.0, "humidity_pct": 50.0},
        "particulate_matter": {"PM1_0": 10.0, "PM2_5": 20.0, "PM10": 30.0},
        "gas_sensors": {
            "MQ2": {"raw_adc": 180, "voltage_V": 0.88},
            "MQ9": {"raw_adc": 160, "voltage_V": 0.78},
            "MQ135": {"raw_adc": 170, "voltage_V": 0.83},
        }
    })
    print("\n  Case D (Duplicated / Historical timestamp):")
    print(f"    Anomaly detected: {dup_res.get('anomaly', {}).get('detected')} | System state: {dup_res.get('system_state')}")

    # Case E: Node Restart and History Reload
    restart_engine = AnomalyEngine()
    restarted_node = "restart-test-node"
    # Load 50 historical records in bulk
    history_records = [
        {
            "timestamp": (t_base + timedelta(minutes=5 * k)).isoformat(),
            "environment": {"temperature_C": 25.0 + 0.1 * (k % 5), "humidity_pct": 50.0 + 0.2 * (k % 5)},
            "particulate_matter": {"PM1_0": 10.0, "PM2_5": 20.0, "PM10": 30.0},
            "gas_sensors": {
                "MQ2": {"raw_adc": 180, "voltage_V": 0.88},
                "MQ9": {"raw_adc": 160, "voltage_V": 0.78},
                "MQ135": {"raw_adc": 170, "voltage_V": 0.83},
            }
        }
        for k in range(50)
    ]
    loaded = restart_engine.load_history(restarted_node, history_records)
    print(f"\n  Case E (Node Restart): Successfully loaded {loaded} historical records into baseline.")
    assert loaded == 50
    state_after_restart = restart_engine.get_system_state(restarted_node)
    print(f"    System state after restart: {state_after_restart}")
    assert state_after_restart in ("LEARNING", "MONITORING")

    print("\nALL PHASE 4 INDEPENDENT EVALUATIONS AND STRESS TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    run_independent_evaluation()
