import pytest
from datetime import datetime, timezone, timedelta
from app.schemas.sensor import SensorPayload
from app.schemas.inference import InferenceResult, InferenceStatus
from app.services.pipeline import ModularPipeline

def get_valid_payload(timestamp_delta_min=0, pm25=15.0, mq2_v=1.5, temp=25.0):
    now = datetime.now(timezone.utc) + timedelta(minutes=timestamp_delta_min)
    
    # Maintain PM ordering: PM1.0 <= PM2.5 <= PM10
    pm1_0 = min(10.0, pm25)
    pm10 = max(20.0, pm25)
    
    return SensorPayload(**{
        "node_id": "test-node",
        "timestamp": now.isoformat(),
        "environment": {"temperature_C": temp, "humidity_pct": 50.0},
        "particulate_matter": {"PM1_0": pm1_0, "PM2_5": pm25, "PM10": pm10},
        "gas_sensors": {
            "MQ2": {"raw_adc": 300, "voltage_V": mq2_v},
            "MQ9": {"raw_adc": 300, "voltage_V": 1.5},
            "MQ135": {"raw_adc": 300, "voltage_V": 1.5},
        }
    })

def get_inference(status="safe", conf=0.9, uncertainty=0.1):
    return InferenceResult(
        status=InferenceStatus.SUCCESS,
        gas_class="CleanAir",
        class_confidence=conf,
        class_probabilities={"CleanAir": conf},
        safety_status=status,
        safety_confidence=conf,
        uncertainty=uncertainty,
        inference_time_ms=10.0
    )

def test_pipeline_normal_data():
    pipeline = ModularPipeline()
    payload = get_valid_payload()
    inference = get_inference()
    
    result = pipeline.process(payload, inference)
    
    # 1. Health should be OK
    assert result.health.status == "ok"
    assert len(result.health.issues) == 0
    
    # 2. Anomaly should be False (first reading sets baseline)
    assert result.anomaly.is_anomalous is False
    
    # 3. Forecast should be None (no prior history for persistence)
    assert result.forecast.pm2_5_persistence is None
    
    # 4. Advisory should be NORMAL
    assert result.advisory.level == "NORMAL"

def test_pipeline_stale_data():
    pipeline = ModularPipeline()
    # 2 hours old
    payload = get_valid_payload(timestamp_delta_min=-120)
    inference = get_inference()
    
    result = pipeline.process(payload, inference)
    
    assert result.health.status == "stale"
    assert "stale" in result.health.issues[0].lower()
    assert result.advisory.level == "MAINTENANCE"

def test_pipeline_invalid_sensor_data():
    pipeline = ModularPipeline()
    # Railed sensor
    payload = get_valid_payload(mq2_v=0.0) 
    inference = get_inference()
    
    result = pipeline.process(payload, inference)
    
    assert result.health.status == "degraded"
    assert any("railed to GND" in msg for msg in result.health.issues)
    assert result.advisory.level == "MAINTENANCE"

def test_pipeline_anomaly_detection():
    pipeline = ModularPipeline()
    inference = get_inference()
    
    # Send baseline readings
    for _ in range(5):
        pipeline.process(get_valid_payload(mq2_v=1.5), inference)
        
    # Send anomalous reading
    payload = get_valid_payload(mq2_v=4.0)
    result = pipeline.process(payload, inference)
    
    assert result.anomaly.is_anomalous is True
    assert any("mq2_v" in dev for dev in result.anomaly.deviations)
    assert result.advisory.level == "CAUTION"

def test_pipeline_pm_forecast():
    pipeline = ModularPipeline()
    inference = get_inference()
    
    # First reading (sets baseline)
    pipeline.process(get_valid_payload(pm25=12.0), inference)
    
    # Second reading (should get forecast = 12.0)
    result = pipeline.process(get_valid_payload(pm25=15.0), inference)
    
    assert result.forecast.pm2_5_persistence == 12.0

def test_pipeline_hazardous_advisory():
    pipeline = ModularPipeline()
    payload = get_valid_payload(pm25=200.0) # Elevated PM
    inference = get_inference(status="unsafe", conf=0.95, uncertainty=0.1) # Confident unsafe
    
    result = pipeline.process(payload, inference)
    
    assert result.advisory.level == "WARNING"
    assert any("Elevated particulate matter" in msg for msg in result.advisory.messages)
    assert any("Hazardous environmental gas profile" in msg for msg in result.advisory.messages)

def test_pipeline_uncertain_hazardous_advisory():
    pipeline = ModularPipeline()
    payload = get_valid_payload(pm25=15.0) 
    inference = get_inference(status="unsafe", conf=0.55, uncertainty=0.8) # Uncertain unsafe
    
    result = pipeline.process(payload, inference)
    
    # Should downgrade to CAUTION because of high uncertainty
    assert result.advisory.level == "CAUTION"
    assert any("confidence is low" in msg for msg in result.advisory.messages)
