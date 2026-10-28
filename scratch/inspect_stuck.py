import sys
from pathlib import Path

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
for i, rec in enumerate(records):
    res = engine.analyse("eval-delhi-888", rec)
    if 8758 <= i <= 8768:
        fault = rec.get("provenance", {}).get("fault")
        is_hw = res.get("is_hardware_fault")
        src = res.get("anomaly_source")
        det = res.get("anomaly_source_detail")
        ev = res.get("sensor_evidence", {}).get("MQ2_voltage_V", {})
        ev_adc = res.get("sensor_evidence", {}).get("MQ2_raw_adc", {})
        mq9_ev = res.get("sensor_evidence", {}).get("MQ9_voltage_V", {})
        mq135_ev = res.get("sensor_evidence", {}).get("MQ135_voltage_V", {})
        pm_ev = res.get("sensor_evidence", {}).get("PM2_5", {})
        print(f"idx={i} | fault={fault} | is_hw={is_hw} | src={src}")
        print(f"   detail: {det}")
        print(f"   MQ2_v: act={ev.get('actual')}, exp={ev.get('expected')}, sc={ev.get('score')}, hlth={ev.get('sensor_health')}")
        print(f"   MQ2_adc: act={ev_adc.get('actual')}, exp={ev_adc.get('expected')}, sc={ev_adc.get('score')}, hlth={ev_adc.get('sensor_health')}")
        print(f"   MQ9_v sc={mq9_ev.get('score')} | MQ135_v sc={mq135_ev.get('score')} | PM2.5 sc={pm_ev.get('score')}")
