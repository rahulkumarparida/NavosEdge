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
