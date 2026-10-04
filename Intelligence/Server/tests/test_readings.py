"""
Tests for sensor reading submission, validation, and retrieval.
"""

import pytest
from tests.conftest import valid_sensor_payload


@pytest.mark.asyncio
async def test_submit_valid_reading(client, sample_payload):
    node_id = sample_payload["node_id"]
    resp = await client.post(f"/api/v1/nodes/{node_id}/readings", json=sample_payload)
    assert resp.status_code == 201
    data = resp.json()
    assert set(data) == {"aqi", "pm", "temperature_C", "humidity_pct", "predictions", "advisory"}
    assert data["aqi"] is not None
    assert isinstance(data["aqi"], (int, float))
    assert data["pm"] == {"PM1_0": 18.4, "PM2_5": 42.7, "PM10": 76.3}
    assert data["temperature_C"] == 31.2
    assert data["humidity_pct"] == 68.5
    assert set(data["predictions"]) == {"source", "forecast"}
    assert set(data["predictions"]["source"]) == {"value", "confidence"}
    assert set(data["predictions"]["forecast"]) == {"value", "confidence"}
    assert set(data["advisory"]) == {"severity", "advice", "actions", "weather_advice"}


@pytest.mark.asyncio
async def test_intelligence_response_does_not_leak_internal_fields(client, sample_payload):
    response = await client.post(
        f"/api/v1/nodes/{sample_payload['node_id']}/readings", json=sample_payload
    )
    body = response.json()
    serialized = str(body)
    for forbidden in ("raw_adc", "voltage_V", "class_probabilities", "sensor_evidence", "model_version"):
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_submit_reading_node_id_mismatch(client, sample_payload):
    resp = await client.post("/api/v1/nodes/wrong-node/readings", json=sample_payload)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_submit_reading_missing_fields(client):
    incomplete = {
        "node_id": "test-node-01",
        "timestamp": "2026-09-19T10:30:00",
    }
    resp = await client.post("/api/v1/nodes/test-node-01/readings", json=incomplete)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_reading_invalid_temperature(client):
    payload = valid_sensor_payload()
    payload["environment"]["temperature_C"] = 200.0  # Out of range
    node_id = payload["node_id"]
    resp = await client.post(f"/api/v1/nodes/{node_id}/readings", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_reading_invalid_humidity(client):
    payload = valid_sensor_payload()
    payload["environment"]["humidity_pct"] = -5.0  # Out of range
    node_id = payload["node_id"]
    resp = await client.post(f"/api/v1/nodes/{node_id}/readings", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_reading_invalid_adc(client):
    payload = valid_sensor_payload()
    payload["gas_sensors"]["MQ2"]["raw_adc"] = 2000  # Out of 10-bit range
    node_id = payload["node_id"]
    resp = await client.post(f"/api/v1/nodes/{node_id}/readings", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_reading_invalid_pm_ordering(client):
    payload = valid_sensor_payload()
    # PM1.0 > PM2.5 — should violate the constraint
    payload["particulate_matter"]["PM1_0"] = 100.0
    payload["particulate_matter"]["PM2_5"] = 20.0
    payload["particulate_matter"]["PM10"] = 10.0
    node_id = payload["node_id"]
    resp = await client.post(f"/api/v1/nodes/{node_id}/readings", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_reading_invalid_node_id_chars(client):
    payload = valid_sensor_payload()
    payload["node_id"] = "bad node!@#"
    resp = await client.post("/api/v1/nodes/bad%20node!@%23/readings", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_submit_reading_future_timestamp(client):
    payload = valid_sensor_payload()
    payload["timestamp"] = "2099-12-31T23:59:59"
    node_id = payload["node_id"]
    resp = await client.post(f"/api/v1/nodes/{node_id}/readings", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_latest_after_submit(client, sample_payload):
    node_id = sample_payload["node_id"]
    await client.post(f"/api/v1/nodes/{node_id}/readings", json=sample_payload)

    resp = await client.get(f"/api/v1/nodes/{node_id}/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {"aqi", "pm", "temperature_C", "humidity_pct", "predictions", "advisory"}


@pytest.mark.asyncio
async def test_get_latest_unknown_node(client):
    resp = await client.get("/api/v1/nodes/nonexistent-node/latest")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_node_status_after_submit(client, sample_payload):
    node_id = sample_payload["node_id"]
    await client.post(f"/api/v1/nodes/{node_id}/readings", json=sample_payload)

    resp = await client.get(f"/api/v1/nodes/{node_id}/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_id"] == node_id
    assert data["total_readings"] >= 1
    assert data["inference_available"] is False  # no model loaded


@pytest.mark.asyncio
async def test_get_node_status_unknown_node(client):
    resp = await client.get("/api/v1/nodes/nonexistent-node/status")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_forward_to_manager_payload_structure(sample_payload):
    """Verifies that _forward_to_manager generates the expected telemetry format."""
    from unittest.mock import AsyncMock, patch, MagicMock
    from app.services.processing import ProcessingService
    from app.schemas.sensor import SensorPayload
    from app.schemas.intelligence import IntelligenceResult, IntelligencePredictions, PredictionOutput
    from app.advisory.schemas import AdvisoryResult

    payload = SensorPayload(**sample_payload)
    result = IntelligenceResult(
        aqi=45.0,
        pm={"PM1_0": 10.0, "PM2_5": 20.0, "PM10": 30.0},
        temperature_C=25.0,
        humidity_pct=60.0,
        predictions=IntelligencePredictions(
            source=PredictionOutput(value="Traffic", confidence=0.85),
            forecast=PredictionOutput(value=None, confidence=None),
        ),
        advisory=AdvisoryResult(
            severity="NORMAL",
            advice="Good air",
            actions=[],
            weather_advice="Comfortable conditions",
        ),
    )

    ps = ProcessingService(
        inference_adapter=MagicMock(),
        node_registry=MagicMock(),
        storage=MagicMock(),
        event_service=MagicMock(),
        anomaly_engine=MagicMock(),
    )

    posted_url = None
    posted_json = None

    async def mock_post(url, json=None, **kwargs):
        nonlocal posted_url, posted_json
        posted_url = url
        posted_json = json
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "OK"
        return mock_resp

    mock_client = AsyncMock()
    mock_client.post.side_effect = mock_post
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        await ps._forward_to_manager(payload.node_id, payload, result)

    assert posted_url == f"http://127.0.0.1:8430/api/v1/nodes/{payload.node_id}/telemetry"
    assert posted_json is not None
    assert posted_json["node_id"] == payload.node_id
    assert posted_json["temperature_C"] == 25.0
    assert posted_json["humidity_pct"] == 60.0
    assert posted_json["aqi"] == 45.0
    assert posted_json["pm"] == {"PM1_0": 10.0, "PM2_5": 20.0, "PM10": 30.0}
    assert posted_json["predictions"]["source"]["value"] == "Traffic"
    assert posted_json["predictions"]["source"]["confidence"] == 0.85
    assert posted_json["advisory"]["severity"] == "NORMAL"


@pytest.mark.asyncio
async def test_forward_to_manager_resilience_on_failure(sample_payload):
    """Verifies that _forward_to_manager survives network errors and 500 status gracefully."""
    from unittest.mock import AsyncMock, patch, MagicMock
    from app.services.processing import ProcessingService
    from app.schemas.sensor import SensorPayload
    from app.schemas.intelligence import IntelligenceResult, IntelligencePredictions, PredictionOutput
    from app.advisory.schemas import AdvisoryResult

    payload = SensorPayload(**sample_payload)
    result = IntelligenceResult(
        aqi=50.0,
        pm={"PM1_0": 10.0, "PM2_5": 25.0, "PM10": 40.0},
        temperature_C=22.0,
        humidity_pct=50.0,
        predictions=IntelligencePredictions(
            source=PredictionOutput(value="Unknown", confidence=None),
            forecast=PredictionOutput(value=None, confidence=None),
        ),
        advisory=AdvisoryResult(
            severity="NORMAL",
            advice="Ok",
            actions=[],
            weather_advice="Mild",
        ),
    )

    ps = ProcessingService(
        inference_adapter=MagicMock(),
        node_registry=MagicMock(),
        storage=MagicMock(),
        event_service=MagicMock(),
        anomaly_engine=MagicMock(),
    )

    # 1. Connection error must not raise
    fail_client = AsyncMock()
    fail_client.post.side_effect = Exception("Connection refused to Manager")
    fail_client.__aenter__.return_value = fail_client
    fail_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=fail_client):
        await ps._forward_to_manager(payload.node_id, payload, result)

    # 2. HTTP 500 error must not raise
    err_resp = MagicMock()
    err_resp.status_code = 500
    err_resp.text = "Internal Server Error"
    err_client = AsyncMock()
    err_client.post.return_value = err_resp
    err_client.__aenter__.return_value = err_client
    err_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=err_client):
        await ps._forward_to_manager(payload.node_id, payload, result)

