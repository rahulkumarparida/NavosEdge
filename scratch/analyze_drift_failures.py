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

reasons = {
    "mq135_score_below_3": 0,
    "pm_score_ge_1_5": 0,
    "max_other_ge_1_5": 0,
    "other": 0,
}

drift_failures = []

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
            
            subreasons = []
            if mq135_sc < 3.0:
                subreasons.append(f"mq135_score_low({mq135_sc:.2f}<3.0)")
            if max_other >= 1.5:
                subreasons.append(f"max_other_gas_ge_1.5({max_other:.2f})")
            if pm_sc >= 1.5:
                subreasons.append(f"pm_score_ge_1.5({pm_sc:.2f})")
                
            drift_failures.append({
                "idx": i,
                "ts": rec["timestamp"],
                "src": res.get("anomaly_source"),
                "mq135_sc": mq135_sc,
                "max_other_gas": max_other,
                "pm_sc": pm_sc,
                "reasons": subreasons,
            })

print(f"Total drift failures: {len(drift_failures)}")
from collections import Counter
counts = Counter()
for f in drift_failures:
    key = tuple(sorted([r.split("(")[0] for r in f["reasons"]]))
    counts[key] += 1

print("\nBreakdown of failure reasons for the 151 undetected drift readings:")
for k, v in counts.most_common():
    print(f"  {k}: {v}")

print("\nFirst 10 failures:")
for f in drift_failures[:10]:
    print(f"  idx={f['idx']} | src={f['src']} | mq135={f['mq135_sc']:.2f} | other_gas={f['max_other_gas']:.2f} | pm={f['pm_sc']:.2f} | reasons={f['reasons']}")

print("\nFailures where mq135_sc >= 3.0 (i.e. drift was clearly anomalous but blocked from HW detection):")
blocked_failures = [f for f in drift_failures if f['mq135_sc'] >= 3.0]
print(f"Count: {len(blocked_failures)}")
blocked_counts = Counter()
for f in blocked_failures:
    key = tuple(sorted([r.split("(")[0] for r in f["reasons"]]))
    blocked_counts[key] += 1
for k, v in blocked_counts.most_common():
    print(f"  {k}: {v}")

print("\nSample blocked failures:")
for f in blocked_failures[:10]:
    print(f"  idx={f['idx']} | src={f['src']} | mq135={f['mq135_sc']:.2f} | other_gas={f['max_other_gas']:.2f} | pm={f['pm_sc']:.2f} | reasons={f['reasons']}")
