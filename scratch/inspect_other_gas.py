import sys
from pathlib import Path
import json

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

drift_other_gas_cases = []

for i, rec in enumerate(records):
    res = engine.analyse("eval-delhi-888", rec)
    fault = rec.get("provenance", {}).get("fault")
    if fault == "sensor_drift":
        is_hw = res.get("is_hardware_fault", False)
        if not is_hw:
            ev = res.get("sensor_evidence", {})
            mq135_sc = max(ev.get("MQ135_voltage_V", {}).get("score", 0), ev.get("MQ135_raw_adc", {}).get("score", 0))
            mq2_sc = max(ev.get("MQ2_voltage_V", {}).get("score", 0), ev.get("MQ2_raw_adc", {}).get("score", 0))
            mq9_sc = max(ev.get("MQ9_voltage_V", {}).get("score", 0), ev.get("MQ9_raw_adc", {}).get("score", 0))
            pm_sc = max(
                ev.get("PM1_0", {}).get("score", 0),
                ev.get("PM2_5", {}).get("score", 0),
                ev.get("PM10", {}).get("score", 0),
            )
            max_other = max(mq2_sc, mq9_sc)
            if max_other >= 1.5:
                drift_other_gas_cases.append({
                    "idx": i,
                    "mq135_sc": mq135_sc,
                    "mq2_sc": mq2_sc,
                    "mq9_sc": mq9_sc,
                    "max_other": max_other,
                    "pm_sc": pm_sc,
                    "src": res.get("anomaly_source"),
                })

print(f"Total cases with max_other >= 1.5: {len(drift_other_gas_cases)}")
for c in drift_other_gas_cases[:15]:
    print(f"idx={c['idx']} | mq135={c['mq135_sc']:.2f} | mq2={c['mq2_sc']:.2f} | mq9={c['mq9_sc']:.2f} | max_other={c['max_other']:.2f} | pm={c['pm_sc']:.2f} | src={c['src']}")
