from Simulator.historical_generator import GenerationConfig, HistoricalDatasetGenerator
from scratch.test_anomaly_improvements import RefinedAnomalyEngine

gen_config = GenerationConfig(node_id='test-inspect', days=35, seed=42, start_date='2024-09-01', location='bhubaneswar', inject_faults=True)
records = HistoricalDatasetGenerator(gen_config).generate_all()
engine = RefinedAnomalyEngine()

for r in records:
    res = engine.analyse('test-inspect', r)
    if r['timestamp'] == '2024-09-16T02:25:00+00:00':
        print('Evidence for MQ135:')
        print(res['sensor_evidence']['MQ135_voltage_V'])
        print(res['sensor_evidence']['MQ135_raw_adc'])
        print('Anomaly source:', res.get('anomaly_source'))
        print('Detail:', res.get('anomaly_source_detail'))
        break
