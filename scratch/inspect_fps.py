from Simulator.historical_generator import GenerationConfig, HistoricalDatasetGenerator
from scratch.test_anomaly_improvements import RefinedAnomalyEngine
import pandas as pd

gen_config = GenerationConfig(node_id='test-inspect', days=35, seed=42, start_date='2024-09-01', location='bhubaneswar', inject_faults=True)
records = HistoricalDatasetGenerator(gen_config).generate_all()
engine = RefinedAnomalyEngine()

reasons = []
for i, r in enumerate(records):
    prov = r.get("provenance", {})
    fault = prov.get("fault")
    scen = prov.get("scenario")
    is_hw = (fault is not None and fault != "warmup")
    
    res = engine.analyse('test-inspect', r)
    source = res.get('anomaly_source')
    detail = res.get('anomaly_source_detail')
    is_hw_alert = (source in ('SENSOR_FAULT', 'MIXED'))
    
    if not is_hw and is_hw_alert and scen in ('combustion_smoke', 'mixed_pollution'):
        reasons.append({
            "idx": i,
            "ts": r['timestamp'],
            "scen": scen,
            "detail": detail,
            "source": source,
        })

df = pd.DataFrame(reasons)
print(f"Total FP inspected: {len(df)}")
if len(df) > 0:
    print(df['detail'].value_counts())
    print("\nFirst 5 details:")
    for _, row in df.head(5).iterrows():
        print(f"  [{row['scen']}] {row['ts']}: {row['detail']}")
