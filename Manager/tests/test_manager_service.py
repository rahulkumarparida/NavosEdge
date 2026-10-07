"""
Manager Server Unit & Resiliency Tests
"""

import math
from pathlib import Path
import pytest
import asyncio
from datetime import datetime, timezone

from app.manager_service import ManagerService, normalize_telemetry, safe_float
from app.models import NodeState, NodeTelemetryPayload, OverallData, OverviewResponse
from app.storage import ManagerStorage


def test_safe_float_handling():
    """Validates safe_float across all boundary conditions."""
    # Null / None handling
    assert safe_float(None, default=0.0) == 0.0
    assert safe_float(None, default=None) is None
    assert safe_float("null", default=0.0) == 0.0
    assert safe_float("none", default=0.0) == 0.0
    assert safe_float("", default=0.0) == 0.0

    # Legitimate zero preservation
    assert safe_float(0, default=0.0) == 0.0
    assert safe_float(0.0, default=0.0) == 0.0
    assert safe_float(0.0, default=None) == 0.0
    assert safe_float("0", default=None) == 0.0
    assert safe_float("0.0", default=None) == 0.0

    # Negative numbers preservation
    assert safe_float(-15.5, default=0.0) == -15.5
    assert safe_float("-15.5", default=0.0) == -15.5

    # Positive numbers
    assert safe_float(42.5, default=0.0) == 42.5
    assert safe_float("42.5", default=0.0) == 42.5

    # NaN / Invalid types
    assert safe_float(float("nan"), default=0.0) == 0.0
    assert safe_float("nan", default=None) is None
    assert safe_float("invalid_string", default=0.0) == 0.0
    assert safe_float([1, 2], default=0.0) == 0.0
    assert safe_float({"a": 1}, default=None) is None


def test_normalize_telemetry_full():
    """Validates normalization of a complete telemetry dictionary."""
    data = {
        "node_id": "navos-01",
        "location": "Custom Lab",
        "aqi": 55.5,
        "pm": {"PM1_0": 5.0, "PM2_5": 15.0, "PM10": 30.0},
        "temperature_C": 25.5,
        "humidity_pct": 60.0,
        "predictions": {
            "source": {"value": "Traffic", "confidence": 0.85},
            "forecast": {"value": None, "confidence": None},
        },
        "advisory": {"severity": "NORMAL", "advice": "Good air"},
    }
    norm = normalize_telemetry(data)
    assert norm["node_id"] == "navos-01"
    assert norm["location"] == "Custom Lab"
    assert norm["status"] == "active"
    assert norm["aqi"] == 55.5
    assert norm["pm"]["PM1_0"] == 5.0
    assert norm["pm"]["PM2_5"] == 15.0
    assert norm["pm"]["PM10"] == 30.0
    assert norm["temperature_C"] == 25.5
    assert norm["humidity_pct"] == 60.0
    assert norm["source_prediction"] == "Traffic"
    assert norm["source_confidence"] == 0.85
    assert norm["advisory"]["severity"] == "NORMAL"


def test_normalize_telemetry_nulls_and_empty():
    """Validates normalization with null environmental values and missing fields."""
    norm = normalize_telemetry({"temperature_C": None, "humidity_pct": None}, node_id="navos-null")
    assert norm["node_id"] == "navos-null"
    assert norm["temperature_C"] == 0.0
    assert norm["humidity_pct"] == 0.0
    assert norm["aqi"] is None
    assert norm["pm"] == {"PM1_0": 0.0, "PM2_5": 0.0, "PM10": 0.0}
    assert norm["source_prediction"] == "unknown"
    assert norm["source_confidence"] is None


def test_normalize_telemetry_preserves_zero_and_negative():
    """Validates that 0.0 and valid negative temperatures are preserved."""
    norm = normalize_telemetry(
        {
            "temperature_C": -7.5,
            "humidity_pct": 0.0,
            "aqi": 0.0,
            "pm": {"PM1_0": 0.0, "PM2_5": 0.0, "PM10": 0.0},
        },
        node_id="navos-zero",
    )
    assert norm["temperature_C"] == -7.5
    assert norm["humidity_pct"] == 0.0
    assert norm["aqi"] == 0.0
    assert norm["pm"]["PM2_5"] == 0.0


def test_manager_regional_aggregation_math():
    """Validates regional aggregation averages and maximum AQI."""
    service = ManagerService(storage=ManagerStorage(file_path=Path("/tmp/test_agg_state.json")))

    # Node 1: AQI 50, temp -5.0, hum 40, PM2.5 10
    t1 = {
        "node_id": "node-1",
        "aqi": 50.0,
        "pm": {"PM1_0": 5.0, "PM2_5": 10.0, "PM10": 20.0},
        "temperature_C": -5.0,
        "humidity_pct": 40.0,
    }
    # Node 2: AQI 100, temp 15.0, hum 60, PM2.5 30
    t2 = {
        "node_id": "node-2",
        "aqi": 100.0,
        "pm": {"PM1_0": 15.0, "PM2_5": 30.0, "PM10": 40.0},
        "temperature_C": 15.0,
        "humidity_pct": 60.0,
    }

    asyncio.run(service.ingest_telemetry(t1))
    asyncio.run(service.ingest_telemetry(t2))

    overview = service.get_overview()
    assert overview.active_nodes == 2
    assert overview.overall.aqi == 100.0
    # Average temp: (-5.0 + 15.0) / 2 = 5.0
    assert overview.overall.temperature_C == 5.0
    # Average hum: (40.0 + 60.0) / 2 = 50.0
    assert overview.overall.humidity_pct == 50.0
    # Average PM2.5: (10.0 + 30.0) / 2 = 20.0
    assert overview.overall.PM2_5 == 20.0


def test_manager_overview_with_null_and_zero_aqi():
    """Validates that AQI=0 is preserved in max calculation and null AQI is ignored."""
    service = ManagerService(storage=ManagerStorage(file_path=Path("/tmp/test_zero_aqi.json")))

    # Node with AQI=0.0
    asyncio.run(service.ingest_telemetry({"node_id": "n-zero", "aqi": 0.0}))
    overview = service.get_overview()
    assert overview.overall.aqi == 0.0

    # Add node with AQI=None
    asyncio.run(service.ingest_telemetry({"node_id": "n-none", "aqi": None}))
    overview2 = service.get_overview()
    assert overview2.overall.aqi == 0.0  # Max of [0.0] is still 0.0


def test_manager_storage_persistence(tmp_path):
    """Validates state file save and load."""
    state_file = tmp_path / "storage_test.json"
    storage = ManagerStorage(file_path=state_file)
    service1 = ManagerService(storage=storage)

    asyncio.run(service1.ingest_telemetry({"node_id": "persist-node", "temperature_C": 28.0}))
    assert state_file.exists()

    service2 = ManagerService(storage=storage)
    assert "persist-node" in service2.nodes
    node = service2.get_node("persist-node")
    assert node.temperature_C == 28.0
    assert node.status == "inactive"  # Restored nodes start inactive until new reading


@pytest.mark.asyncio
async def test_manager_sse_broadcasting():
    """Validates SSE subscription and event delivery."""
    service = ManagerService(storage=ManagerStorage(file_path=Path("/tmp/test_sse_state.json")))
    queue = await service.subscribe()

    await service.ingest_telemetry({"node_id": "sse-node", "aqi": 30.0})
    msg = await asyncio.wait_for(queue.get(), timeout=2.0)
    assert "event: telemetry_update" in msg
    assert "sse-node" in msg

    await service.unsubscribe(queue)
    assert len(service.subscribers) == 0


def test_normalize_telemetry_flexible_pm_and_calculated_aqi():
    """Validates that various PM naming formats and missing AQI calculate EPA AQI correctly."""
    # Compact format with pm25 and pm10
    data = {
        "node_id": "compact-pm-node",
        "pm25": 55.4,
        "pm10": 100.0,
    }
    norm = normalize_telemetry(data)
    assert norm["pm"]["PM2_5"] == 55.4
    assert norm["pm"]["PM10"] == 100.0
    # AQI calculated via EPA formula (55.4 PM2.5 maps to AQI ~150)
    assert norm["aqi"] is not None
    assert 140.0 <= norm["aqi"] <= 160.0

    # particulate_matter dict with dotted keys
    data2 = {
        "node_id": "alt-pm-node",
        "particulate_matter": {
            "PM1.0": 12.0,
            "PM2.5": 25.0,
            "PM10": 45.0,
        },
    }
    norm2 = normalize_telemetry(data2)
    assert norm2["pm"]["PM1_0"] == 12.0
    assert norm2["pm"]["PM2_5"] == 25.0
    assert norm2["pm"]["PM10"] == 45.0
    assert norm2["aqi"] is not None


def test_overview_preserves_metrics_when_nodes_become_inactive(tmp_path):
    """Validates that when all nodes are marked inactive, overview maintains the last known statistics."""
    state_file = tmp_path / "inactive_test.json"
    service = ManagerService(storage=ManagerStorage(file_path=state_file))

    # Ingest node data
    asyncio.run(service.ingest_telemetry({
        "node_id": "temp-node",
        "aqi": 88.0,
        "pm": {"PM1_0": 10.0, "PM2_5": 20.0, "PM10": 30.0},
        "temperature_C": 22.0,
        "humidity_pct": 55.0,
    }))

    # Manually mark as inactive
    service.nodes["temp-node"]["status"] = "inactive"
    overview = service.get_overview()

    assert overview.active_nodes == 0
    assert overview.inactive_nodes == 1
    # Should fall back to the known nodes instead of zeroing out
    assert overview.overall.aqi == 88.0
    assert overview.overall.PM2_5 == 20.0
    assert overview.overall.PM10 == 30.0

