"""
Run Stress Tests (Test 2 Cases A, B, C, D, E) on TargetedSensorHealthCheckerV3.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

root_dir = Path(".").resolve()
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "Intelligence" / "Server"))

from scratch.test_targeted_v3 import TargetedAnomalyEngineV3

stress_engine = TargetedAnomalyEngineV3()
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
print("Case A (Mixed concurrent smoke + MQ9 GND rail fault):")
print(f"  Source: {mix_res.get('anomaly_source')} | Detail: {mix_res.get('anomaly_source_detail')}")
print(f"  is_hardware_fault: {mix_res.get('is_hardware_fault')} | is_environmental_event: {mix_res.get('is_environmental_event')}")
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
print("\nCase B (Sudden genuine PM dust surge PM10=850):")
print(f"  Source: {dust_res.get('anomaly_source')} | Detail: {dust_res.get('anomaly_source_detail')}")
print(f"  is_hardware_fault: {dust_res.get('is_hardware_fault')} | is_environmental_event: {dust_res.get('is_environmental_event')}")
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
print("\nCase C (Extreme Monsoon Humidity 96.5%):")
print(f"  Source: {monsoon_res.get('anomaly_source')} | Detail: {monsoon_res.get('anomaly_source_detail')}")
print(f"  is_hardware_fault: {monsoon_res.get('is_hardware_fault')}")
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
print("\nCase D (Duplicated / Historical timestamp):")
print(f"  Anomaly detected: {dup_res.get('anomaly', {}).get('detected')} | System state: {dup_res.get('system_state')}")

# Case E: Node Restart and History Reload
restart_engine = TargetedAnomalyEngineV3()
restarted_node = "restart-test-node"
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
print(f"\nCase E (Node Restart): Successfully loaded {loaded} historical records into baseline.")
assert loaded == 50
state_after_restart = restart_engine.get_system_state(restarted_node)
print(f"  System state after restart: {state_after_restart}")
assert state_after_restart in ("LEARNING", "MONITORING")

print("\nALL STRESS TESTS PASSED WITH TARGETED FIX V3!")
