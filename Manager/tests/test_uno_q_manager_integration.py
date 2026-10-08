"""
NavosEdge — Intelligence ↔ Manager Dual Integration & Resilience Test Suite
Validates:
1. Normal telemetry
2. temperature_C = null
3. humidity_pct = null
4. Both environmental values null
5. Missing temperature/humidity fields
6. Valid zero and negative values
7. Missing optional telemetry fields
8. Intelligence endpoint unavailable
9. Intelligence endpoint returning malformed data
10. Push telemetry path
11. Pull polling path
12. Multiple nodes where one node has invalid data
13. Node recovery after temporary failure
14. Timeout/inactive-node handling
15. Manager continues running after a bad telemetry payload
16. Push / Pull state normalization consistency
"""

import sys
from pathlib import Path

# Ensure Manager directory is in sys.path BEFORE app imports
_cur = Path(__file__).resolve()
project_root = _cur.parent
while project_root != project_root.parent and not (project_root / "Manager").is_dir():
    project_root = project_root.parent
manager_dir = project_root / "Manager"
intel_dir = project_root / "Intelligence" / "Server"

if str(manager_dir) in sys.path:
    sys.path.remove(str(manager_dir))
sys.path.insert(0, str(manager_dir))

# Evict cached 'app' modules if previous test imported Intelligence/Server/app
for mod_name in list(sys.modules.keys()):
    if mod_name == "app" or mod_name.startswith("app."):
        sys.modules.pop(mod_name, None)

import asyncio
import os
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

from app.config import UNO_Q_BASE_URL, UNO_Q_POLL_INTERVAL_S, UNO_Q_POLL_ENABLED, INACTIVE_TIMEOUT_SECONDS
from app.manager_service import ManagerService, normalize_telemetry, safe_float
from app.models import NodeState, OverviewResponse, NodeTelemetryPayload
from app.storage import ManagerStorage
from app.main import create_app


def test_01_normal_telemetry(tmp_path):
    """1. Normal telemetry ingestion."""
    storage = ManagerStorage(file_path=tmp_path / "test_normal.json")
    service = ManagerService(storage=storage)

    payload = NodeTelemetryPayload(
        node_id="navos-01",
        location="Bhubaneswar",
        aqi=42.0,
        pm={"PM1_0": 5.0, "PM2_5": 12.0, "PM10": 25.0},
        temperature_C=26.5,
        humidity_pct=55.0,
        predictions={"source": {"value": "Traffic", "confidence": 0.88}},
        advisory={"severity": "NORMAL", "advice": "Good air"},
    )
    state = asyncio.run(service.ingest_telemetry(payload))
    assert state.status == "active"
    assert state.temperature_C == 26.5
    assert state.humidity_pct == 55.0
    assert state.aqi == 42.0
    assert state.pm["PM2_5"] == 12.0
    assert state.source_prediction == "Traffic"
    assert state.source_confidence == 0.88

    overview = service.get_overview()
    assert overview.active_nodes == 1
    assert overview.overall.aqi == 42.0
    assert overview.overall.temperature_C == 26.5
    assert overview.overall.humidity_pct == 55.0


def test_02_temperature_c_null(tmp_path):
    """2. temperature_C = null safely normalizes to 0.0."""
    storage = ManagerStorage(file_path=tmp_path / "test_temp_null.json")
    service = ManagerService(storage=storage)

    payload = NodeTelemetryPayload(
        node_id="navos-02",
        temperature_C=None,
        humidity_pct=60.0,
        aqi=35.0,
    )
    state = asyncio.run(service.ingest_telemetry(payload))
    assert state.temperature_C == 0.0
    assert state.humidity_pct == 60.0
    assert state.status == "active"


def test_03_humidity_pct_null(tmp_path):
    """3. humidity_pct = null safely normalizes to 0.0."""
    storage = ManagerStorage(file_path=tmp_path / "test_hum_null.json")
    service = ManagerService(storage=storage)

    payload = NodeTelemetryPayload(
        node_id="navos-03",
        temperature_C=24.0,
        humidity_pct=None,
    )
    state = asyncio.run(service.ingest_telemetry(payload))
    assert state.temperature_C == 24.0
    assert state.humidity_pct == 0.0
    assert state.status == "active"


def test_04_both_environmental_values_null(tmp_path):
    """4. Both environmental values null."""
    storage = ManagerStorage(file_path=tmp_path / "test_both_null.json")
    service = ManagerService(storage=storage)

    payload = NodeTelemetryPayload(
        node_id="navos-04",
        temperature_C=None,
        humidity_pct=None,
    )
    state = asyncio.run(service.ingest_telemetry(payload))
    assert state.temperature_C == 0.0
    assert state.humidity_pct == 0.0
    assert state.status == "active"


def test_05_missing_temperature_humidity_fields(tmp_path):
    """5. Missing temperature/humidity fields entirely (empty payload)."""
    storage = ManagerStorage(file_path=tmp_path / "test_missing_fields.json")
    service = ManagerService(storage=storage)

    # Empty payload dict
    state = asyncio.run(service.ingest_telemetry({}, node_id="navos-05"))
    assert state.temperature_C == 0.0
    assert state.humidity_pct == 0.0
    assert state.aqi is None
    assert state.pm["PM2_5"] == 0.0
    assert state.status == "active"


def test_06_valid_zero_and_negative_values(tmp_path):
    """6. Valid zero and negative values must be preserved."""
    storage = ManagerStorage(file_path=tmp_path / "test_zero_neg.json")
    service = ManagerService(storage=storage)

    # Legitimate 0.0 values
    t_zero = NodeTelemetryPayload(
        node_id="node-zero",
        temperature_C=0.0,
        humidity_pct=0.0,
        aqi=0.0,
        pm={"PM1_0": 0.0, "PM2_5": 0.0, "PM10": 0.0},
    )
    state_zero = asyncio.run(service.ingest_telemetry(t_zero))
    assert state_zero.temperature_C == 0.0
    assert state_zero.humidity_pct == 0.0
    assert state_zero.aqi == 0.0
    assert state_zero.pm["PM2_5"] == 0.0

    # Negative temperature
    t_neg = NodeTelemetryPayload(
        node_id="node-neg",
        temperature_C=-8.5,
        humidity_pct=45.0,
    )
    state_neg = asyncio.run(service.ingest_telemetry(t_neg))
    assert state_neg.temperature_C == -8.5

    # Check aggregation preserves zero AQI
    overview = service.get_overview()
    # AQI max among [0.0, None] is 0.0
    assert overview.overall.aqi == 0.0
    # Average temp: (0.0 + -8.5) / 2 = -4.2
    assert overview.overall.temperature_C == -4.2


def test_07_missing_optional_telemetry_fields(tmp_path):
    """7. Missing optional telemetry fields (aqi, pm, predictions, advisory)."""
    storage = ManagerStorage(file_path=tmp_path / "test_missing_optional.json")
    service = ManagerService(storage=storage)

    state = asyncio.run(service.ingest_telemetry({"node_id": "opt-node"}))
    assert state.aqi is None  # Genuinely optional, should NOT be 0.0
    assert state.pm == {"PM1_0": 0.0, "PM2_5": 0.0, "PM10": 0.0}
    assert state.source_prediction == "unknown"
    assert state.source_confidence is None
    assert state.predictions == {}
    assert state.advisory == {}


def test_08_intelligence_endpoint_unavailable(tmp_path):
    """8. Intelligence endpoint unavailable."""
    storage = ManagerStorage(file_path=tmp_path / "test_unavail.json")
    service = ManagerService(storage=storage)

    asyncio.run(service.register_node("uno-q-001", "UNO Q Lab"))
    assert service.get_node("uno-q-001").status == "active"

    # Ingest some telemetry to verify it is NOT erased on poll failure
    asyncio.run(service.ingest_telemetry({"node_id": "uno-q-001", "temperature_C": 25.0, "aqi": 50.0}))
    assert service.get_node("uno-q-001").temperature_C == 25.0

    os.environ["NAVOS_UNO_Q_URL"] = "http://127.0.0.1:59999"
    try:
        overview = asyncio.run(service.poll_uno_q())
        assert overview.active_nodes == 0
        assert overview.inactive_nodes == 1
        node = service.get_node("uno-q-001")
        assert node.status == "inactive"
        # Telemetry retained!
        assert node.temperature_C == 25.0
        assert node.aqi == 50.0
    finally:
        os.environ.pop("NAVOS_UNO_Q_URL", None)


@pytest.mark.asyncio
async def test_09_intelligence_endpoint_returning_malformed_data(tmp_path):
    """9. Intelligence endpoint returning malformed data."""
    storage = ManagerStorage(file_path=tmp_path / "test_malformed.json")
    service = ManagerService(storage=storage)

    # Mock response for /api/v1/nodes returning malformed non-JSON
    nodes_resp_mock = MagicMock()
    nodes_resp_mock.status_code = 200
    nodes_resp_mock.json.side_effect = ValueError("Invalid JSON")

    mock_client = AsyncMock()
    mock_client.get.return_value = nodes_resp_mock
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        # Should not raise exception
        overview = await service.poll_uno_q()
        assert isinstance(overview, OverviewResponse)


def test_10_push_telemetry_path(tmp_path):
    """10. Push telemetry path via HTTP POST."""
    app = create_app()
    app.state.manager_service = ManagerService(storage=ManagerStorage(file_path=tmp_path / "test_push.json"))
    with TestClient(app) as client:
        # Normal payload
        resp1 = client.post(
            "/api/v1/nodes/push-01/telemetry",
            json={
                "temperature_C": 28.5,
                "humidity_pct": 52.0,
                "aqi": 60.0,
                "pm": {"PM1_0": 5.0, "PM2_5": 15.0, "PM10": 30.0},
            },
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["node_id"] == "push-01"
        assert data1["temperature_C"] == 28.5
        assert data1["status"] == "active"

        # Null environmental values payload
        resp2 = client.post(
            "/api/v1/nodes/push-02/telemetry",
            json={"temperature_C": None, "humidity_pct": None},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["temperature_C"] == 0.0
        assert data2["humidity_pct"] == 0.0

        # Empty payload
        resp3 = client.post("/api/v1/nodes/push-03/telemetry", json={})
        assert resp3.status_code == 200
        data3 = resp3.json()
        assert data3["temperature_C"] == 0.0
        assert data3["humidity_pct"] == 0.0


@pytest.mark.asyncio
async def test_11_pull_polling_path(tmp_path):
    """11. Pull polling path via HTTP GET to Intelligence Server."""
    storage = ManagerStorage(file_path=tmp_path / "test_pull.json")
    service = ManagerService(storage=storage)

    nodes_mock = MagicMock()
    nodes_mock.status_code = 200
    nodes_mock.json.return_value = {"nodes": [{"node_id": "uno-q-pull", "status": "active"}]}

    latest_mock = MagicMock()
    latest_mock.status_code = 200
    latest_mock.json.return_value = {
        "aqi": 48.0,
        "pm": {"PM1_0": 4.0, "PM2_5": 11.0, "PM10": 22.0},
        "temperature_C": 23.5,
        "humidity_pct": 50.0,
        "predictions": {"source": {"value": "Clean Indoor", "confidence": 0.95}},
        "advisory": {"severity": "NORMAL", "advice": "Clean"},
    }

    async def mock_get(url, **kwargs):
        if url.endswith("/api/v1/nodes"):
            return nodes_mock
        elif "/latest" in url:
            return latest_mock
        raise ValueError(f"Unexpected url: {url}")

    mock_client = AsyncMock()
    mock_client.get.side_effect = mock_get
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        overview = await service.poll_uno_q()

    assert overview.active_nodes == 1
    node = service.get_node("uno-q-pull")
    assert node.status == "active"
    assert node.temperature_C == 23.5
    assert node.aqi == 48.0


@pytest.mark.asyncio
async def test_12_multiple_nodes_one_invalid(tmp_path):
    """12. Multiple nodes where one node has invalid data does NOT abort others."""
    storage = ManagerStorage(file_path=tmp_path / "test_multi_node.json")
    service = ManagerService(storage=storage)

    nodes_mock = MagicMock()
    nodes_mock.status_code = 200
    nodes_mock.json.return_value = {
        "nodes": [
            {"node_id": "node-good-1", "status": "active"},
            {"node_id": "node-bad-2", "status": "active"},
            {"node_id": "node-good-3", "status": "active"},
        ]
    }

    latest_good_1 = MagicMock()
    latest_good_1.status_code = 200
    latest_good_1.json.return_value = {"aqi": 30.0, "temperature_C": 22.0, "humidity_pct": 50.0}

    # Bad node: returns malformed json or 500 error
    latest_bad_2 = MagicMock()
    latest_bad_2.status_code = 500

    latest_good_3 = MagicMock()
    latest_good_3.status_code = 200
    latest_good_3.json.return_value = {"aqi": 60.0, "temperature_C": 25.0, "humidity_pct": 55.0}

    async def mock_get(url, **kwargs):
        if url.endswith("/api/v1/nodes"):
            return nodes_mock
        elif "node-good-1" in url:
            return latest_good_1
        elif "node-bad-2" in url:
            return latest_bad_2
        elif "node-good-3" in url:
            return latest_good_3
        raise ValueError(f"Unexpected url: {url}")

    mock_client = AsyncMock()
    mock_client.get.side_effect = mock_get
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        overview = await service.poll_uno_q()

    # Good nodes are active, bad node failure was caught without terminating the loop
    assert overview.active_nodes == 2
    assert service.get_node("node-good-1").status == "active"
    assert service.get_node("node-good-3").status == "active"
    assert service.get_node("node-bad-2") is None or service.get_node("node-bad-2").status != "active"


@pytest.mark.asyncio
async def test_13_node_recovery_after_temporary_failure(tmp_path):
    """13. Node recovery after temporary failure."""
    storage = ManagerStorage(file_path=tmp_path / "test_recovery.json")
    service = ManagerService(storage=storage)

    nodes_mock = MagicMock()
    nodes_mock.status_code = 200
    nodes_mock.json.return_value = {"nodes": [{"node_id": "recover-node", "status": "active"}]}

    latest_mock = MagicMock()
    latest_mock.status_code = 200
    latest_mock.json.return_value = {"aqi": 40.0, "temperature_C": 24.0, "humidity_pct": 50.0}

    async def mock_get(url, **kwargs):
        if url.endswith("/api/v1/nodes"):
            return nodes_mock
        return latest_mock

    mock_client = AsyncMock()
    mock_client.get.side_effect = mock_get
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    # Cycle 1: Success
    with patch("httpx.AsyncClient", return_value=mock_client):
        await service.poll_uno_q()
    assert service.get_node("recover-node").status == "active"
    assert service.get_node("recover-node").aqi == 40.0

    # Cycle 2: Temporary failure (network error)
    fail_client = AsyncMock()
    fail_client.get.side_effect = Exception("Temporary network outage")
    fail_client.__aenter__.return_value = fail_client
    fail_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=fail_client):
        await service.poll_uno_q()
    node_after_fail = service.get_node("recover-node")
    assert node_after_fail.status == "inactive"
    assert node_after_fail.aqi == 40.0  # Telemetry NOT erased!

    # Cycle 3: Recovery
    latest_mock.json.return_value = {"aqi": 42.0, "temperature_C": 24.5, "humidity_pct": 51.0}
    with patch("httpx.AsyncClient", return_value=mock_client):
        await service.poll_uno_q()
    node_recovered = service.get_node("recover-node")
    assert node_recovered.status == "active"
    assert node_recovered.aqi == 42.0


@pytest.mark.asyncio
async def test_14_timeout_inactive_node_handling(tmp_path):
    """14. Timeout and inactive node handling (including resilience against corrupted timestamps)."""
    storage = ManagerStorage(file_path=tmp_path / "test_timeout.json")
    service = ManagerService(storage=storage)

    # Ingest active node with old timestamp
    old_time = (datetime.now(timezone.utc) - timedelta(seconds=INACTIVE_TIMEOUT_SECONDS + 10)).isoformat()
    await service.ingest_telemetry({
        "node_id": "timeout-node",
        "timestamp": old_time,
        "temperature_C": 20.0,
    })
    assert service.get_node("timeout-node").status == "active"

    # Add second node with corrupted unparseable timestamp
    service.nodes["corrupt-node"] = {
        "node_id": "corrupt-node",
        "location": "Corrupt Lab",
        "status": "active",
        "last_seen": "not-a-valid-timestamp",
        "temperature_C": 0.0,
    }

    # Run check_node_timeouts: must not crash and must update both nodes to inactive
    await service.check_node_timeouts()
    assert service.get_node("timeout-node").status == "inactive"
    assert service.nodes["corrupt-node"]["status"] == "inactive"


def test_15_manager_continues_running_after_bad_telemetry_payload(tmp_path):
    """15. Manager continues running after a bad telemetry payload."""
    app = create_app()
    app.state.manager_service = ManagerService(storage=ManagerStorage(file_path=tmp_path / "test_bad.json"))
    with TestClient(app) as client:
        # Send bad payload
        resp_bad = client.post(
            "/api/v1/nodes/bad-node/telemetry",
            content="[1, 2, 3]",
            headers={"Content-Type": "application/json"},
        )
        assert resp_bad.status_code == 422

        # Verify manager continues running and serves subsequent requests normally
        resp_good = client.post(
            "/api/v1/nodes/good-node/telemetry",
            json={"temperature_C": 25.0, "humidity_pct": 50.0},
        )
        assert resp_good.status_code == 200
        assert resp_good.json()["status"] == "active"

        # Verify overview endpoint is healthy
        resp_ov = client.get("/api/v1/overview")
        assert resp_ov.status_code == 200
        assert resp_ov.json()["active_nodes"] >= 1


@pytest.mark.asyncio
async def test_16_push_pull_consistency(tmp_path):
    """16. Both Push and Pull produce identical normalized NodeState."""
    storage1 = ManagerStorage(file_path=tmp_path / "test_push_state.json")
    service_push = ManagerService(storage=storage1)

    storage2 = ManagerStorage(file_path=tmp_path / "test_pull_state.json")
    service_pull = ManagerService(storage=storage2)

    raw_reading = {
        "aqi": 52.0,
        "pm": {"PM1_0": 6.0, "PM2_5": 14.0, "PM10": 28.0},
        "temperature_C": 27.0,
        "humidity_pct": 55.0,
        "predictions": {
            "source": {"value": "Traffic", "confidence": 0.82},
            "forecast": {"value": None, "confidence": None},
        },
        "advisory": {"severity": "NORMAL", "advice": "Nominal"},
    }

    # 1. Push
    push_state = await service_push.ingest_telemetry(raw_reading, node_id="test-node")

    # 2. Pull
    nodes_mock = MagicMock()
    nodes_mock.status_code = 200
    nodes_mock.json.return_value = {"nodes": [{"node_id": "test-node", "status": "active"}]}

    latest_mock = MagicMock()
    latest_mock.status_code = 200
    latest_mock.json.return_value = raw_reading

    async def mock_get(url, **kwargs):
        if url.endswith("/api/v1/nodes"):
            return nodes_mock
        return latest_mock

    mock_client = AsyncMock()
    mock_client.get.side_effect = mock_get
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("httpx.AsyncClient", return_value=mock_client):
        await service_pull.poll_uno_q()

    pull_state = service_pull.get_node("test-node")

    # Verify identical normalized fields
    assert push_state.aqi == pull_state.aqi == 52.0
    assert push_state.pm == pull_state.pm
    assert push_state.temperature_C == pull_state.temperature_C == 27.0
    assert push_state.humidity_pct == pull_state.humidity_pct == 55.0
    assert push_state.source_prediction == pull_state.source_prediction == "Traffic"
    assert push_state.source_confidence == pull_state.source_confidence == 0.82
    assert push_state.status == pull_state.status == "active"


def test_17_ip_configuration_dashboard_api(tmp_path):
    """17. Dynamic IP configuration change from Manager dashboard API."""
    app = create_app()
    service = ManagerService(storage=ManagerStorage(file_path=tmp_path / "test_ip_cfg.json"))
    app.state.manager_service = service
    with TestClient(app) as client:
        with patch.object(service, "poll_uno_q", new_callable=AsyncMock) as mock_poll:
            mock_poll.return_value = OverviewResponse(active_nodes=1, total_nodes=1)

            # 1. GET IP configuration
            get_resp = client.get("/api/v1/config/ip")
            assert get_resp.status_code == 200
            get_data = get_resp.json()
            assert "current_ip" in get_data
            assert "base_url" in get_data

            # 2. POST IP configuration
            post_resp = client.post("/api/v1/config/ip", json={"ip": "192.168.1.120", "port": 8420})
            assert post_resp.status_code == 200
            post_data = post_resp.json()
            assert post_data["current_ip"] == "192.168.1.120"
            assert post_data["port"] == 8420
            assert post_data["base_url"] == "http://192.168.1.120:8420"
            assert service.uno_q_ip == "192.168.1.120"
            mock_poll.assert_awaited()

            # 3. Node-specific IP configuration
            node_resp = client.post("/api/v1/nodes/uno-q-001/ip", json={"ip": "10.103.68.200", "port": 8420})
            assert node_resp.status_code == 200
            assert node_resp.json()["current_ip"] == "10.103.68.200"

            # 4. URL string input parsing
            url_resp = client.post("/api/v1/config/ip", json={"ip": "http://10.103.68.99:8435"})
            assert url_resp.status_code == 200
            assert url_resp.json()["current_ip"] == "10.103.68.99"
            assert url_resp.json()["port"] == 8435
            assert url_resp.json()["base_url"] == "http://10.103.68.99:8435"

            # 5. Empty IP rejection
            empty_resp = client.post("/api/v1/config/ip", json={"ip": "   "})
            assert empty_resp.status_code == 422


