from Simulator.historical_generator import GenerationConfig, HistoricalDatasetGenerator
from scratch.test_anomaly_improvements import RefinedAnomalyEngine

gen_config = GenerationConfig(node_id='test-seasonal', days=5, seed=42, start_date='2024-09-01', location='bhubaneswar', inject_faults=False)
# Let's inspect records in seasonal drift or see what happened
engine = RefinedAnomalyEngine()
records = HistoricalDatasetGenerator(gen_config).generate_all()

# Find out what triggered HW alert in seasonal_drift
for i, r in enumerate(records):
    res = engine.analyse('test-seasonal', r)
    source = res.get('anomaly_source')
    detail = res.get('anomaly_source_detail')
    if source in ('SENSOR_FAULT', 'MIXED'):
        print(f"Record {i} ({r['timestamp']}): source={source}")
        print(f"  detail: {detail}")
        scores = {k: v.get('score') for k, v in res.get('sensor_evidence', {}).items() if v.get('score', 0) > 1.5}
        issues = {k: v.get('sensor_health') for k, v in res.get('sensor_evidence', {}).items() if v.get('sensor_health') != 'GOOD'}
        print(f"  scores > 1.5: {scores}")
        print(f"  issues: {issues}")
        break
