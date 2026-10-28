import sys
from pathlib import Path
root_dir = Path(".").resolve()
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "Intelligence" / "Server"))

from scratch.test_targeted_v2 import TargetedAnomalyEngineV2
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
engine = TargetedAnomalyEngineV2()

fps = []
for i, rec in enumerate(records):
    res = engine.analyse("eval-delhi-888", rec)
    prov = rec.get("provenance", {})
    fault = prov.get("fault")
    scen = prov.get("scenario")
    is_hw = (fault is not None and fault != "warmup")
    src = res.get("anomaly_source", "")
    is_hw_alert = res.get("is_hardware_fault", False) or (src in ("SENSOR_FAULT", "MIXED"))
    if not is_hw and is_hw_alert and scen == "sensor_health_and_faults":
        fps.append({
            "idx": i,
            "ts": rec["timestamp"],
            "fault": fault,
            "src": src,
            "detail": res.get("anomaly_source_detail"),
            "ev": res.get("sensor_evidence"),
        })

print(f"Total FPs in sensor_health_and_faults: {len(fps)}")
indices = [f["idx"] for f in fps]
print(f"Index ranges: min={min(indices)}, max={max(indices)}")
import collections
ts_hours = collections.Counter([f["ts"][:13] for f in fps])
print("FPs by hour:")
for h, c in sorted(ts_hours.items()):
    print(f"  {h}: {c} FPs")

print("\nSample FPs:")
for f in fps[:5]:
    print(f"idx={f['idx']} | ts={f['ts']} | fault={f['fault']} | src={f['src']} | detail={f['detail']}")
    for k, v in f["ev"].items():
        if v.get("score", 0) >= 2.0 or v.get("sensor_health") != "GOOD":
            print(f"   {k}: act={v.get('actual')}, exp={v.get('expected')}, res={v.get('residual')}, sc={v.get('score')}, hlth={v.get('sensor_health')}")
