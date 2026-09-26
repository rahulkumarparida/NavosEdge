"""Tests for the AQI calculation, persistence, update, and API endpoint."""

import os
from datetime import datetime, timezone
import pytest
from app.aqi.calculator import AQICalculator
from app.aqi.schemas import AQICalculationResult, LatestAQIResponse
from app.aqi.store import AQIStore
from app.aqi.service import AQIService
from tests.conftest import valid_sensor_payload


def test_aqi_calculator_epa():
    calc = AQICalculator(standard="EPA")
    # Test Good range
    res = calc.calculate(pm1_0=5.0, pm2_5=10.0, pm10=20.0)
    assert res.status == "available"
    assert res.category == "Good"
    assert res.dominant_pollutant == "PM2_5"
    assert res.sub_indices["PM2_5"] <= 50.0
    assert res.pm == {"PM1_0": 5.0, "PM2_5": 10.0, "PM10": 20.0}

    # Test Moderate range
    res_mod = calc.calculate(pm1_0=15.0, pm2_5=25.0, pm10=80.0)
    assert res_mod.category == "Moderate"
    assert res_mod.sub_indices["PM2_5"] > 50.0

    # Test Unhealthy for Sensitive Groups range
    res_unhealthy = calc.calculate(pm1_0=30.0, pm2_5=40.0, pm10=100.0)
    assert res_unhealthy.category == "Unhealthy for Sensitive Groups"
    assert 101.0 <= res_unhealthy.aqi <= 150.0


def test_aqi_calculator_cpcb():
    calc = AQICalculator(standard="CPCB")
    res = calc.calculate(pm1_0=10.0, pm2_5=20.0, pm10=40.0)
    assert res.category in ("Good", "Satisfactory")


def test_aqi_store_persistence(tmp_path):
    storage_file = tmp_path / "aqi_latest.json"
    store = AQIStore(storage_path=storage_file)

    # Initial state: empty
    assert store.get_latest() is None

    # Save a result
    now = datetime.now(timezone.utc)
    res = AQICalculationResult(
        status="available",
        aqi=75.5,
        category="Moderate",
        dominant_pollutant="PM2_5",
        pm={"PM1_0": 15.0, "PM2_5": 23.5, "PM10": 45.0},
        sub_indices={"PM1_0": 56.0, "PM2_5": 75.5, "PM10": 41.0},
        timestamp=now,
        node_id="test-node-01",
    )
    store.save_latest(res)

    # Check disk file created
    assert storage_file.exists()

    # Load into fresh store
    store2 = AQIStore(storage_path=storage_file)
    loaded = store2.load_latest()
    assert loaded is not None
    assert loaded.aqi == 75.5
    assert loaded.node_id == "test-node-01"


def test_aqi_store_update(tmp_path):
    storage_file = tmp_path / "aqi_latest.json"
    store = AQIStore(storage_path=storage_file)

    now = datetime.now(timezone.utc)
    res1 = AQICalculationResult(
        status="available",
        aqi=45.0,
        category="Good",
        dominant_pollutant="PM2_5",
        pm={"PM1_0": 5.0, "PM2_5": 10.0, "PM10": 20.0},
        sub_indices={"PM1_0": 25.0, "PM2_5": 45.0, "PM10": 18.0},
        timestamp=now,
        node_id="test-node-01",
    )
    store.save_latest(res1)
    assert store.get_latest().aqi == 45.0

    # Overwrite with newer reading
    res2 = AQICalculationResult(
        status="available",
        aqi=120.0,
        category="Unhealthy for Sensitive Groups",
        dominant_pollutant="PM2_5",
        pm={"PM1_0": 30.0, "PM2_5": 43.0, "PM10": 90.0},
        sub_indices={"PM1_0": 89.0, "PM2_5": 120.0, "PM10": 68.0},
        timestamp=now,
        node_id="test-node-01",
    )
    store.save_latest(res2)
    assert store.get_latest().aqi == 120.0

    # Reload from disk to ensure disk was updated
    store3 = AQIStore(storage_path=storage_file)
    loaded = store3.load_latest()
    assert loaded.aqi == 120.0


@pytest.mark.asyncio
async def test_aqi_latest_endpoint_not_available(client):
    # Reset AQI store state for this test if app state is available
    transport = getattr(client, "_transport", None)
    app = getattr(transport, "app", None)
    if app and hasattr(app.state, "aqi_service"):
        svc = app.state.aqi_service
        svc.store._latest = None
        svc.store._latest_by_node.clear()
        if svc.store.storage_path.exists():
            svc.store.storage_path.unlink()

    resp = await client.get("/aqi/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "not_available"
    assert data["detail"] is not None


@pytest.mark.asyncio
async def test_aqi_latest_endpoint_after_submission(client, sample_payload):
    node_id = sample_payload["node_id"]

    # Submit sensor reading
    submit_resp = await client.post(f"/api/v1/nodes/{node_id}/readings", json=sample_payload)
    assert submit_resp.status_code == 201

    # Query GET /aqi/latest
    resp = await client.get("/aqi/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "available"
    assert data["aqi"] is not None
    assert isinstance(data["aqi"], (int, float))
    assert data["category"] is not None
    assert data["dominant_pollutant"] is not None
    assert set(data["pm"]) == {"PM1_0", "PM2_5", "PM10"}
    assert data["node_id"] == node_id

    # Query GET /api/v1/aqi/latest alias endpoint
    resp_alias = await client.get("/api/v1/aqi/latest")
    assert resp_alias.status_code == 200
    assert resp_alias.json()["status"] == "available"
