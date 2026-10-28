import json

with open("test_data/anomaly_baseline_delhi/baseline_failed_cases.json", "r") as f:
    data = json.load(f)

fps = data["false_positives"]
for fp in fps:
    print("=" * 60)
    print(f"FP idx={fp['idx']} | ts={fp['timestamp']} | scen={fp['scenario']} | src={fp['anomaly_source']}")
    print(f"detail: {fp['anomaly_source_detail']}")
    print(f"score={fp['score']}")
    ev = fp.get("sensor_evidence", {})
    for fn in ["MQ2_voltage_V", "MQ2_raw_adc", "MQ9_voltage_V", "MQ9_raw_adc", "MQ135_voltage_V", "MQ135_raw_adc", "PM2_5"]:
        if fn in ev:
            print(f"  {fn:<16s}: act={ev[fn]['actual']}, exp={ev[fn]['expected']}, res={ev[fn]['residual']}, sc={ev[fn]['score']}, hlth={ev[fn]['sensor_health']}")
