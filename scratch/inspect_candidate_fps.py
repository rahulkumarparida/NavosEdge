"""
Inspect why candidate had 139 FPs in sensor_health_and_faults.
"""
import sys
from pathlib import Path
root_dir = Path(".").resolve()
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "Intelligence" / "Server"))

from scratch.test_targeted_fix import TargetedAnomalyEngine
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
records = HistoricalDatasetGenerator(gen_config).generate_all()
engine = TargetedAnomalyEngine()

fps = []
for i, rec in enumerate(records):
    res = engine.analyse("eval-delhi-888", rec)
    prov = rec.get("provenance", {})
    fault = prov.get("fault")
    scen = prov.get("scenario")
    is_hw = (fault is not None and fault != "warmup")
    src = res.get("anomaly_source", "")
    is_hw_alert = res.get("is_hardware_fault", False) or (src in ("SENSOR_FAULT", "MIXED"))
    if not is_hw and is_hw_alert:
        fps.append({
            "idx": i,
            "ts": rec["timestamp"],
            "scen": scen,
            "fault": fault,
            "src": src,
            "detail": res.get("anomaly_source_detail"),
            "ev": res.get("sensor_evidence"),
        })

print(f"Total FPs: {len(fps)}")
print(f"FPs in traffic: {len([f for f in fps if f['scen'] == 'traffic'])}")
print(f"FPs in sensor_health_and_faults: {len([f for f in fps if f['scen'] == 'sensor_health_and_faults'])}")

print("\nSample FPs in sensor_health_and_faults:")
sh_fps = [f for f in fps if f['scen'] == 'sensor_health_and_faults']
for f in sh_fps[:10]:
    print(f"idx={f['idx']} | ts={f['ts']} | fault={f['fault']} | src={f['src']} | detail={f['detail']}")
    for k, v in f["ev"].items():
        if v.get("score", 0) >= 2.0 or v.get("sensor_health") != "GOOD":
            print(f"   {k}: act={v.get('actual')}, exp={v.get('expected')}, res={v.get('residual')}, sc={v.get('score')}, hlth={v.get('sensor_health')}")

print("\nSample FPs in traffic:")
tr_fps = [f for f in fps if f['scen'] == 'traffic']
for f in tr_fps[:5]:
    print(f"idx={f['idx']} | ts={f['ts']} | fault={f['fault']} | src={f['src']} | detail={f['detail']}")
    for k, v in f["ev"].items():
        if v.get("score", 0) >= 2.0 or v.get("sensor_health") != "GOOD":
            print(f"   {k}: act={v.get('actual')}, exp={v.get('expected')}, res={v.get('residual')}, sc={v.get('score')}, hlth={v.get('sensor_health')}")
