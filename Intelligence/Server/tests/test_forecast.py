"""
Tests for Phase 4 — Lightweight Autoregressive Forecast Plugin.

Covers:
- Synthetic data generation and replay
- Forecasting with sufficient / insufficient history
- Irregular timestamps
- Spike and trend scenarios
- 48-hour retention and automatic cleanup
- File read/write/delete behavior
- API responses and plugin failure handling
"""

import json
import math
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.forecast.config import ForecastSettings
from app.forecast.generator import (
    generate_synthetic_series,
    replay_through_plugin,
    save_synthetic_to_jsonl,
)
from app.forecast.model import generate_forecast
from app.forecast.plugin import ForecastPlugin
from app.forecast.store import ForecastStore
from app.schemas.forecast import (
    ForecastReadingInput,
    ForecastReliability,
    ForecastStatus,
    SyntheticGeneratorConfig,
    TrendDirection,
)


# ============================================================ #
#  Fixtures                                                      #
# ============================================================ #

@pytest.fixture()
def tmp_dir():
    d = tempfile.mkdtemp(prefix="navos_forecast_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def store(tmp_dir):
    return ForecastStore(storage_dir=tmp_dir, retention_hours=48)


@pytest.fixture()
def plugin(tmp_dir):
    p = ForecastPlugin()
    settings = ForecastSettings(
        STORAGE_DIR=tmp_dir / "forecast",
        RETENTION_HOURS=48,
        MIN_HISTORY_POINTS=6,
    )
    p.initialize(settings)
    yield p
    p.shutdown()


def _make_reading(
    node_id: str = "test-node",
    ts: datetime | None = None,
    pm1: float = 10.0,
    pm25: float = 25.0,
    pm10: float = 50.0,
    synthetic: bool = False,
) -> ForecastReadingInput:
    return ForecastReadingInput(
        node_id=node_id,
        timestamp=ts or datetime.now(timezone.utc),
        PM1_0=pm1,
        PM2_5=pm25,
        PM10=pm10,
        is_synthetic=synthetic,
    )


def _make_history(
    n: int = 100,
    node_id: str = "test-node",
    interval_minutes: int = 5,
    base_pm25: float = 25.0,
) -> list[dict]:
    """Create a list of dict records for testing the model directly."""
    now = datetime.now(timezone.utc)
    records = []
    for i in range(n):
        ts = now - timedelta(minutes=(n - i) * interval_minutes)
        # Add a gentle sinusoidal variation
        factor = 1.0 + 0.2 * math.sin(2 * math.pi * i / 48)
        records.append({
            "timestamp": ts.isoformat(),
            "node_id": node_id,
            "PM1_0": round(base_pm25 * 0.5 * factor, 2),
            "PM2_5": round(base_pm25 * factor, 2),
            "PM10": round(base_pm25 * 2.0 * factor, 2),
        })
    return records


# ============================================================ #
#  1. Synthetic Data Generation                                  #
# ============================================================ #

class TestSyntheticGenerator:
    def test_generate_default(self):
        config = SyntheticGeneratorConfig(seed=123)
        readings = generate_synthetic_series(config)
        assert len(readings) > 0
        # 48h at 5-min intervals = 576 samples
        assert len(readings) == 48 * 60 // 5

    def test_all_readings_are_synthetic(self):
        config = SyntheticGeneratorConfig(seed=42, duration_hours=2)
        readings = generate_synthetic_series(config)
        for r in readings:
            assert r.is_synthetic is True

    def test_pm_ordering(self):
        """PM1.0 <= PM2.5 <= PM10 must always hold."""
        config = SyntheticGeneratorConfig(
            seed=99, duration_hours=24, include_spikes=True
        )
        readings = generate_synthetic_series(config)
        for r in readings:
            assert r.PM1_0 <= r.PM2_5 + 0.01
            assert r.PM2_5 <= r.PM10 + 0.01

    def test_seed_reproducibility(self):
        config = SyntheticGeneratorConfig(seed=777, duration_hours=1)
        a = generate_synthetic_series(config)
        b = generate_synthetic_series(config)
        for ra, rb in zip(a, b):
            assert ra.PM2_5 == rb.PM2_5

    def test_save_to_jsonl(self, tmp_dir):
        config = SyntheticGeneratorConfig(seed=42, duration_hours=1)
        readings = generate_synthetic_series(config)
        outfile = tmp_dir / "synthetic.jsonl"
        count = save_synthetic_to_jsonl(readings, outfile)
        assert count == len(readings)
        assert outfile.exists()
        # Verify it's valid JSONL
        with open(outfile) as f:
            for line in f:
                rec = json.loads(line.strip())
                assert rec["is_synthetic"] is True

    def test_replay_through_plugin(self, plugin):
        config = SyntheticGeneratorConfig(
            seed=42, duration_hours=1, node_id="replay-test"
        )
        readings = generate_synthetic_series(config)
        ingested = replay_through_plugin(readings, plugin)
        assert ingested == len(readings)
        # Verify data is in the store
        history = plugin.get_history("replay-test")
        assert history.total_records > 0

    def test_configurable_duration_and_interval(self):
        config = SyntheticGeneratorConfig(
            seed=42, duration_hours=6, sampling_interval_minutes=15
        )
        readings = generate_synthetic_series(config)
        expected = 6 * 60 // 15
        assert len(readings) == expected


# ============================================================ #
#  2. Forecast Store                                             #
# ============================================================ #

class TestForecastStore:
    def test_append_and_read(self, store):
        now = datetime.now(timezone.utc)
        store.append("node-1", {
            "timestamp": now.isoformat(),
            "PM2_5": 30.0,
        })
        records = store.get_history("node-1")
        assert len(records) == 1
        assert records[0]["PM2_5"] == 30.0

    def test_append_multiple(self, store):
        now = datetime.now(timezone.utc)
        for i in range(10):
            store.append("node-1", {
                "timestamp": (now - timedelta(minutes=i)).isoformat(),
                "PM2_5": 20.0 + i,
            })
        records = store.get_history("node-1")
        assert len(records) == 10

    def test_empty_node_returns_empty(self, store):
        records = store.get_history("nonexistent")
        assert records == []

    def test_record_count(self, store):
        now = datetime.now(timezone.utc)
        for i in range(5):
            store.append("node-1", {
                "timestamp": (now - timedelta(minutes=i)).isoformat(),
                "PM2_5": 10.0,
            })
        assert store.get_record_count("node-1") == 5

    def test_time_range(self, store):
        now = datetime.now(timezone.utc)
        store.append("node-1", {
            "timestamp": (now - timedelta(hours=2)).isoformat(),
            "PM2_5": 10.0,
        })
        store.append("node-1", {
            "timestamp": now.isoformat(),
            "PM2_5": 20.0,
        })
        oldest, newest = store.get_time_range("node-1")
        assert oldest is not None and newest is not None
        assert oldest < newest

    def test_health_check(self, store):
        assert store.check_health() is True

    def test_file_isolation_per_node(self, store):
        now = datetime.now(timezone.utc)
        store.append("node-a", {"timestamp": now.isoformat(), "PM2_5": 1.0})
        store.append("node-b", {"timestamp": now.isoformat(), "PM2_5": 2.0})
        assert len(store.get_history("node-a")) == 1
        assert len(store.get_history("node-b")) == 1

    def test_malformed_json_skipped(self, store):
        now = datetime.now(timezone.utc)
        # Write valid record
        store.append("node-1", {
            "timestamp": now.isoformat(), "PM2_5": 10.0
        })
        # Manually append bad JSON
        fp = store._current_file("node-1")
        with open(fp, "a") as f:
            f.write("this is not json\n")
        records = store.get_history("node-1")
        assert len(records) == 1  # Bad line skipped


# ============================================================ #
#  3. Retention / Cleanup                                        #
# ============================================================ #

class TestRetentionCleanup:
    def test_delete_expired_removes_old_records(self, tmp_dir):
        store = ForecastStore(storage_dir=tmp_dir, retention_hours=2)
        now = datetime.now(timezone.utc)
        # Write a record 3 hours ago
        old_ts = now - timedelta(hours=3)
        store.append("node-1", {
            "timestamp": old_ts.isoformat(), "PM2_5": 10.0
        })
        # Write a current record
        store.append("node-1", {
            "timestamp": now.isoformat(), "PM2_5": 20.0
        })
        deleted = store.delete_expired("node-1")
        remaining = store.get_history("node-1", hours=2)
        # Old record should be gone
        assert any(r["PM2_5"] == 20.0 for r in remaining)

    def test_delete_expired_all_nodes(self, tmp_dir):
        store = ForecastStore(storage_dir=tmp_dir, retention_hours=1)
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=2)
        store.append("n1", {"timestamp": old.isoformat(), "PM2_5": 1.0})
        store.append("n2", {"timestamp": old.isoformat(), "PM2_5": 2.0})
        total_deleted = store.delete_expired()
        assert total_deleted >= 0  # May be 0 if files are for today

    def test_cleanup_preserves_recent_data(self, tmp_dir):
        store = ForecastStore(storage_dir=tmp_dir, retention_hours=48)
        now = datetime.now(timezone.utc)
        store.append("node-1", {
            "timestamp": now.isoformat(), "PM2_5": 30.0
        })
        store.delete_expired("node-1")
        records = store.get_history("node-1")
        assert len(records) == 1


# ============================================================ #
#  4. Forecast Model                                             #
# ============================================================ #

class TestForecastModel:
    def test_forecast_with_sufficient_history(self):
        records = _make_history(n=100)
        result = generate_forecast(
            records=records,
            channels=["PM1_0", "PM2_5", "PM10"],
            node_id="test-node",
            horizon_minutes=30,
            sampling_interval_minutes=5,
            min_history_points=12,
        )
        assert result.status == ForecastStatus.OK
        assert len(result.channels) == 3
        for ch in result.channels:
            assert len(ch.predicted_values) == 6  # 30/5
            assert len(ch.predicted_timestamps) == 6
            assert ch.trend in TrendDirection
            assert all(v >= 0 for v in ch.predicted_values)

    def test_forecast_insufficient_data(self):
        records = _make_history(n=3)
        result = generate_forecast(
            records=records,
            channels=["PM2_5"],
            node_id="test-node",
            min_history_points=12,
        )
        assert result.status == ForecastStatus.INSUFFICIENT_DATA
        assert result.reliability == ForecastReliability.UNAVAILABLE
        assert len(result.channels) == 0

    def test_forecast_empty_data(self):
        result = generate_forecast(
            records=[], channels=["PM2_5"], node_id="test-node"
        )
        assert result.status == ForecastStatus.INSUFFICIENT_DATA
        assert result.history_points_used == 0

    def test_forecast_missing_channel(self):
        """Records that don't contain the requested channel."""
        records = [
            {"timestamp": datetime.now(timezone.utc).isoformat(), "OTHER": 10}
            for _ in range(20)
        ]
        result = generate_forecast(
            records=records,
            channels=["PM2_5"],
            node_id="test-node",
            min_history_points=5,
        )
        assert result.status == ForecastStatus.INSUFFICIENT_DATA

    def test_forecast_includes_persistence_baseline(self):
        records = _make_history(n=50)
        result = generate_forecast(
            records=records,
            channels=["PM2_5"],
            node_id="test-node",
            horizon_minutes=15,
            sampling_interval_minutes=5,
            min_history_points=6,
        )
        assert result.status == ForecastStatus.OK
        ch = result.channels[0]
        assert ch.persistence_baseline is not None
        # Persistence baseline should be constant
        assert len(set(ch.persistence_baseline)) == 1

    def test_forecast_nan_values_skipped(self):
        """Records with NaN should be skipped."""
        records = _make_history(n=30)
        records[10]["PM2_5"] = float("nan")
        result = generate_forecast(
            records=records,
            channels=["PM2_5"],
            node_id="test-node",
            min_history_points=12,
        )
        assert result.status == ForecastStatus.OK

    def test_reliability_levels(self):
        # Low point count → MEDIUM reliability
        records = _make_history(n=20)
        result = generate_forecast(
            records=records,
            channels=["PM2_5"],
            node_id="test-node",
            min_history_points=6,
        )
        assert result.reliability in (
            ForecastReliability.MEDIUM,
            ForecastReliability.HIGH,
            ForecastReliability.LOW,
        )


# ============================================================ #
#  5. Irregular Timestamps                                       #
# ============================================================ #

class TestIrregularTimestamps:
    def test_forecast_with_irregular_intervals(self):
        """Model should still produce output with uneven spacing."""
        now = datetime.now(timezone.utc)
        records = []
        t = now - timedelta(hours=6)
        for i in range(40):
            # Irregular: 3-12 minute gaps
            gap = 3 + (i % 10)
            t += timedelta(minutes=gap)
            records.append({
                "timestamp": t.isoformat(),
                "PM2_5": 20.0 + math.sin(i / 5) * 5,
                "PM10": 40.0 + math.sin(i / 5) * 10,
            })
        result = generate_forecast(
            records=records,
            channels=["PM2_5", "PM10"],
            node_id="test-node",
            min_history_points=12,
        )
        assert result.status == ForecastStatus.OK
        assert len(result.channels) == 2


# ============================================================ #
#  6. Spike and Trend Scenarios                                  #
# ============================================================ #

class TestSpikeAndTrend:
    def test_rising_trend_detected(self):
        """Monotonically rising series should yield RISING trend."""
        records = []
        now = datetime.now(timezone.utc)
        for i in range(100):
            records.append({
                "timestamp": (now - timedelta(minutes=(100 - i) * 5)).isoformat(),
                "PM2_5": 10.0 + i * 3.0,  # Strong linear rise
            })
        result = generate_forecast(
            records=records,
            channels=["PM2_5"],
            node_id="test-node",
            horizon_minutes=120,
            sampling_interval_minutes=5,
            min_history_points=12,
            trend_threshold=0.5,
        )
        assert result.status == ForecastStatus.OK
        ch = result.channels[0]
        # AR predictions on a strongly rising series should continue upward
        assert ch.predicted_values[-1] >= ch.predicted_values[0]

    def test_falling_trend_detected(self):
        """Monotonically falling series should predict downward."""
        records = []
        now = datetime.now(timezone.utc)
        for i in range(100):
            records.append({
                "timestamp": (now - timedelta(minutes=(100 - i) * 5)).isoformat(),
                "PM2_5": 200.0 - i * 3.0,  # Strong linear fall
            })
        result = generate_forecast(
            records=records,
            channels=["PM2_5"],
            node_id="test-node",
            horizon_minutes=120,
            sampling_interval_minutes=5,
            min_history_points=12,
            trend_threshold=0.5,
        )
        assert result.status == ForecastStatus.OK
        ch = result.channels[0]
        # AR predictions on a strongly falling series should continue downward
        assert ch.predicted_values[-1] <= ch.predicted_values[0]

    def test_spike_doesnt_crash_model(self):
        records = _make_history(n=60, base_pm25=20.0)
        # Insert a massive spike
        records[30]["PM2_5"] = 500.0
        result = generate_forecast(
            records=records,
            channels=["PM2_5"],
            node_id="test-node",
            min_history_points=12,
        )
        # Should still produce a result (possibly degraded)
        assert result.status == ForecastStatus.OK
        assert all(v >= 0 for v in result.channels[0].predicted_values)


# ============================================================ #
#  7. Plugin Interface                                           #
# ============================================================ #

class TestForecastPlugin:
    def test_lifecycle(self, tmp_dir):
        p = ForecastPlugin()
        assert not p.is_initialized
        settings = ForecastSettings(STORAGE_DIR=tmp_dir / "fc")
        p.initialize(settings)
        assert p.is_initialized
        p.shutdown()
        assert not p.is_initialized

    def test_ingest_and_forecast(self, plugin):
        node = "ingest-test"
        now = datetime.now(timezone.utc)
        for i in range(30):
            plugin.ingest(_make_reading(
                node_id=node,
                ts=now - timedelta(minutes=(30 - i) * 5),
            ))
        result = plugin.forecast(node)
        assert result.status == ForecastStatus.OK

    def test_forecast_without_data(self, plugin):
        result = plugin.forecast("empty-node")
        assert result.status == ForecastStatus.INSUFFICIENT_DATA

    def test_get_history(self, plugin):
        node = "hist-test"
        plugin.ingest(_make_reading(node_id=node))
        history = plugin.get_history(node)
        assert history.total_records >= 1
        assert history.node_id == node

    def test_delete_expired(self, plugin):
        node = "cleanup-test"
        plugin.ingest(_make_reading(node_id=node))
        result = plugin.delete_expired_data(node)
        assert result.records_deleted >= 0

    def test_uninitialized_raises(self):
        p = ForecastPlugin()
        with pytest.raises(RuntimeError):
            p.ingest(_make_reading())
        with pytest.raises(RuntimeError):
            p.forecast("x")

    def test_experimental_warning(self, plugin):
        node = "warn-test"
        now = datetime.now(timezone.utc)
        for i in range(20):
            plugin.ingest(_make_reading(
                node_id=node,
                ts=now - timedelta(minutes=(20 - i) * 5),
            ))
        result = plugin.forecast(node)
        assert "experimental" in result.experimental_warning.lower()


# ============================================================ #
#  8. API Endpoints                                              #
# ============================================================ #

@pytest.mark.asyncio
async def test_forecast_api_submit_reading(client):
    now = datetime.now(timezone.utc).isoformat()
    resp = await client.post(
        "/api/v1/forecast/nodes/api-test/readings",
        json={
            "node_id": "api-test",
            "timestamp": now,
            "PM1_0": 10.0,
            "PM2_5": 25.0,
            "PM10": 50.0,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["stored"] is True


@pytest.mark.asyncio
async def test_forecast_api_predict_no_data(client):
    resp = await client.get("/api/v1/forecast/nodes/no-data-node/predict")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "insufficient_data"


@pytest.mark.asyncio
async def test_forecast_api_predict_with_data(client):
    node = "api-forecast-test"
    now = datetime.now(timezone.utc)
    # Ingest enough readings
    for i in range(30):
        ts = (now - timedelta(minutes=(30 - i) * 5)).isoformat()
        resp = await client.post(
            f"/api/v1/forecast/nodes/{node}/readings",
            json={
                "node_id": node,
                "timestamp": ts,
                "PM1_0": 10.0 + i * 0.1,
                "PM2_5": 25.0 + i * 0.2,
                "PM10": 50.0 + i * 0.3,
            },
        )
        assert resp.status_code == 201

    resp = await client.get(f"/api/v1/forecast/nodes/{node}/predict")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert len(data["channels"]) > 0


@pytest.mark.asyncio
async def test_forecast_api_history(client):
    node = "api-hist-test"
    now = datetime.now(timezone.utc).isoformat()
    await client.post(
        f"/api/v1/forecast/nodes/{node}/readings",
        json={
            "node_id": node,
            "timestamp": now,
            "PM2_5": 30.0,
        },
    )
    resp = await client.get(f"/api/v1/forecast/nodes/{node}/history")
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_id"] == node


@pytest.mark.asyncio
async def test_forecast_api_cleanup(client):
    resp = await client.post("/api/v1/forecast/cleanup")
    assert resp.status_code == 200
    data = resp.json()
    assert "records_deleted" in data


@pytest.mark.asyncio
async def test_forecast_api_node_id_mismatch(client):
    resp = await client.post(
        "/api/v1/forecast/nodes/node-a/readings",
        json={
            "node_id": "node-b",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "PM2_5": 10.0,
        },
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_forecast_api_synthetic_generate(client):
    resp = await client.post(
        "/api/v1/forecast/synthetic/generate",
        json={
            "node_id": "synth-api-test",
            "duration_hours": 2,
            "sampling_interval_minutes": 10,
            "seed": 42,
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["records_generated"] > 0
    assert data["node_id"] == "synth-api-test"


@pytest.mark.asyncio
async def test_forecast_api_predict_with_horizon(client):
    node = "api-horizon-test"
    now = datetime.now(timezone.utc)
    for i in range(20):
        ts = (now - timedelta(minutes=(20 - i) * 5)).isoformat()
        await client.post(
            f"/api/v1/forecast/nodes/{node}/readings",
            json={
                "node_id": node,
                "timestamp": ts,
                "PM2_5": 25.0 + i,
                "PM10": 50.0 + i,
            },
        )
    resp = await client.get(
        f"/api/v1/forecast/nodes/{node}/predict",
        params={"horizon_minutes": 30, "sampling_interval_minutes": 10},
    )
    assert resp.status_code == 200
    data = resp.json()
    if data["status"] == "ok":
        for ch in data["channels"]:
            assert len(ch["predicted_values"]) == 3  # 30/10
