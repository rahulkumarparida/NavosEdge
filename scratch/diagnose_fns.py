import json
from pathlib import Path

with open("test_data/anomaly_baseline_delhi/baseline_failed_cases.json", "r") as f:
    data = json.load(f)

fns = data["false_negatives"]
fps = data["false_positives"]

print(f"Total False Negatives: {len(fns)}")
print(f"Total False Positives: {len(fps)}")

by_fault = {}
for fn in fns:
    fault = fn["fault"]
    by_fault.setdefault(fault, []).append(fn)

for fault, items in by_fault.items():
    print(f"\n==========================================")
    print(f"FAULT TYPE: {fault} (count = {len(items)})")
    print(f"==========================================")
    indices = [x["idx"] for x in items]
    print(f"Indices: {indices[:10]} ... {indices[-5:]}")
    
    # Analyze sources and scores
    sources = {}
    for x in items:
        s = x["anomaly_source"]
        sources[s] = sources.get(s, 0) + 1
    print(f"Assigned anomaly sources: {sources}")
    
    # Detailed sample
    for idx_to_check in [0, 1, 5, len(items)//2, -1]:
        if idx_to_check < len(items):
            s = items[idx_to_check]
            print(f"\n  [Sample item at offset {idx_to_check}] idx={s['idx']}, ts={s['timestamp']}")
            print(f"    source={s['anomaly_source']}, detail={s['anomaly_source_detail']}")
            print(f"    detected={s['detected']}, severity={s['severity']}, score={s['score']}")
            ev = s.get("sensor_evidence", {})
            for fname in ["MQ135_voltage_V", "MQ135_raw_adc", "MQ2_voltage_V", "MQ2_raw_adc", "PM2_5"]:
                if fname in ev:
                    print(f"    {fname:<18s}: actual={ev[fname]['actual']}, exp={ev[fname]['expected']}, res={ev[fname]['residual']}, score={ev[fname]['score']}, health={ev[fname]['sensor_health']}")

print("\n\n==========================================")
print("ANALYZING FALSE POSITIVES")
print("==========================================")
for fp in fps:
    print(f"FP idx={fp['idx']}, ts={fp['timestamp']}, scen={fp['scenario']}, fault={fp['fault']}, source={fp['anomaly_source']}, detail={fp['anomaly_source_detail']}")
