import sys
from pathlib import Path
import numpy as np

root_dir = Path(".").resolve()
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "Intelligence" / "Server"))

from app.anomaly.engine import AnomalyEngine
from Simulator.historical_generator import GenerationConfig, HistoricalDatasetGenerator

gen_config = GenerationConfig(
    node_id="eval-delhi-888",
    days=35,
    sampling_interval_seconds=300.0,
    seed=888,
    start_date="2024-11-01",
    location="delhi",
    inject_faults=True,
)
generator = HistoricalDatasetGenerator(gen_config)
records = generator.generate_all()

engine = AnomalyEngine()
drift_records = []
for i, rec in enumerate(records):
    res = engine.analyse("eval-delhi-888", rec)
    fault = rec.get("provenance", {}).get("fault")
    if fault == "sensor_drift":
        ev = res.get("sensor_evidence", {})
        mq135_ev = ev.get("MQ135_voltage_V", {})
        mq135_adc = ev.get("MQ135_raw_adc", {})
        mq2_ev = ev.get("MQ2_voltage_V", {})
        mq9_ev = ev.get("MQ9_voltage_V", {})
        pm25_ev = ev.get("PM2_5", {})
        is_hw = res.get("is_hardware_fault", False)
        src = res.get("anomaly_source", "")
        drift_records.append({
            "idx": i,
            "ts": rec["timestamp"],
            "is_hw": is_hw,
            "src": src,
            "mq135_act": mq135_ev.get("actual"),
            "mq135_exp": mq135_ev.get("expected"),
            "mq135_res": mq135_ev.get("residual"),
            "mq135_sc": mq135_ev.get("score"),
            "mq2_sc": mq2_ev.get("score"),
            "mq9_sc": mq9_ev.get("score"),
            "pm25_act": pm25_ev.get("actual"),
            "pm25_sc": pm25_ev.get("score"),
        })

print(f"Total drift records: {len(drift_records)}")
detected = [r for r in drift_records if r["is_hw"]]
undetected = [r for r in drift_records if not r["is_hw"]]
print(f"Detected: {len(detected)}, Undetected: {len(undetected)}")
print(f"First detected idx: {detected[0]['idx'] if detected else None} (offset={drift_records.index(detected[0]) if detected else None})")

print("\nFirst 15 drift records:")
for r in drift_records[:15]:
    print(f"idx={r['idx']} | is_hw={r['is_hw']} | src={r['src']} | mq135: act={r['mq135_act']}, exp={r['mq135_exp']}, res={r['mq135_res']}, sc={r['mq135_sc']} | mq2_sc={r['mq2_sc']}, mq9_sc={r['mq9_sc']} | pm25_act={r['pm25_act']}, pm25_sc={r['pm25_sc']}")

print("\nSample around first detection (offset 45 to 55):")
for r in drift_records[45:55]:
    print(f"idx={r['idx']} | is_hw={r['is_hw']} | src={r['src']} | mq135: act={r['mq135_act']}, exp={r['mq135_exp']}, res={r['mq135_res']}, sc={r['mq135_sc']} | mq2_sc={r['mq2_sc']}, mq9_sc={r['mq9_sc']} | pm25_act={r['pm25_act']}, pm25_sc={r['pm25_sc']}")

print("\nSample later in drift (offset 100 to 110):")
for r in drift_records[100:110]:
    print(f"idx={r['idx']} | is_hw={r['is_hw']} | src={r['src']} | mq135: act={r['mq135_act']}, exp={r['mq135_exp']}, res={r['mq135_res']}, sc={r['mq135_sc']} | mq2_sc={r['mq2_sc']}, mq9_sc={r['mq9_sc']} | pm25_act={r['pm25_act']}, pm25_sc={r['pm25_sc']}")
