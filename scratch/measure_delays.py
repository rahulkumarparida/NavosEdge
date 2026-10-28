from Simulator.historical_generator import GenerationConfig, HistoricalDatasetGenerator
from scratch.test_anomaly_improvements import RefinedAnomalyEngine
from datetime import datetime
import numpy as np

gen_config = GenerationConfig(node_id='test-delays', days=35, seed=42, start_date='2024-09-01', location='bhubaneswar', inject_faults=True)
records = HistoricalDatasetGenerator(gen_config).generate_all()
engine = RefinedAnomalyEngine()

episodes = {}
cur_fault = None
start_ts = None

for r in records:
    prov = r.get("provenance", {})
    fault = prov.get("fault")
    is_hw = (fault is not None and fault != "warmup")
    ts = r['timestamp']
    
    if is_hw:
        if cur_fault != fault:
            cur_fault = fault
            start_ts = ts
            episodes[cur_fault] = {
                "start": start_ts,
                "first_detected": None,
                "delay_min": None
            }
        
        res = engine.analyse('test-delays', r)
        src = res.get('anomaly_source')
        if src in ('SENSOR_FAULT', 'MIXED') and episodes[cur_fault]["first_detected"] is None:
            episodes[cur_fault]["first_detected"] = ts
            t0 = datetime.fromisoformat(episodes[cur_fault]["start"])
            t1 = datetime.fromisoformat(ts)
            episodes[cur_fault]["delay_min"] = (t1 - t0).total_seconds() / 60.0
    else:
        if cur_fault is not None:
            cur_fault = None
        engine.analyse('test-delays', r)

print("TIME-TO-FIRST-DETECTION PER FAULT EPISODE:")
for ftype, ep in episodes.items():
    print(f"  {ftype:<15s}: start={ep['start']} | first={ep['first_detected']} | delay={ep['delay_min']:.1f} min")
delays = [ep['delay_min'] for ep in episodes.values() if ep['delay_min'] is not None]
print(f"Mean Time-To-First-Detection: {np.mean(delays):.1f} min")
