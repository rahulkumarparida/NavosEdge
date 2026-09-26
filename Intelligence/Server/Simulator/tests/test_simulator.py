import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.schemas.sensor import SensorPayload
from Simulator.client import ApiResult
from Simulator.generator import ScenarioGenerator, available_scenarios
from Simulator.session import SimulationConfig, SimulationSession, load_dataset, replay_dataset, save_dataset


class FakeClient:
    def __init__(self, failures=0):
        self.failures = failures
        self.submissions = []
        self.health_calls = 0
        self.ready_calls = 0

    async def health(self):
        self.health_calls += 1
        return ApiResult(True, 200, {"status": "ok"})

    async def ready(self):
        self.ready_calls += 1
        return ApiResult(True, 200, {"ready": True})

    async def submit(self, payload):
        self.submissions.append(payload)
        if len(self.submissions) <= self.failures:
            return ApiResult(False, 503, {"error": "unavailable"}, "HTTP 503")
        return ApiResult(True, 201, {"reading_id": str(len(self.submissions))})

    async def status(self, node_id):
        return ApiResult(True, 200, {"node_id": node_id})


class UnavailableClient(FakeClient):
    async def health(self):
        return ApiResult(False, None, None, "connection refused")

    async def latest(self, node_id):
        return ApiResult(True, 200, {"node_id": node_id})


@pytest.mark.parametrize("scenario", [s for s in available_scenarios() if s != "custom"])
def test_scenarios_match_server_schema(scenario):
    generator = ScenarioGenerator(
        "sim-node-01",
        scenario,
        seed=10,
        start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    payload = generator.next_payload(5)
    validated = SensorPayload.model_validate(payload)
    assert validated.node_id == "sim-node-01"
    assert payload["particulate_matter"]["PM1_0"] <= payload["particulate_matter"]["PM2_5"] <= payload["particulate_matter"]["PM10"]


def test_generation_is_reproducible_with_fixed_start_time():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = ScenarioGenerator("sim-node", "traffic", seed=99, start_time=start)
    second = ScenarioGenerator("sim-node", "traffic", seed=99, start_time=start)
    assert [first.next_payload(300) for _ in range(5)] == [second.next_payload(300) for _ in range(5)]


def test_generation_evolves_over_time():
    generator = ScenarioGenerator("sim-node", "traffic", seed=1, start_time=datetime(2026, 1, 1, tzinfo=timezone.utc))
    records = [generator.next_payload(300) for _ in range(10)]
    assert len({record["particulate_matter"]["PM2_5"] for record in records}) > 1


def test_exact_values_are_not_changed_by_scenario_noise_or_spikes():
    generator = ScenarioGenerator(
        "sim-node",
        "combustion",
        seed=1,
        exact={
            "temp": 31.0,
            "humidity": 45.0,
            "pm1": 55.0,
            "pm25": 120.0,
            "pm10": 160.0,
            "mq2": 2.8,
            "mq9": 2.1,
            "mq135": 2.5,
        },
    )
    payload = generator.next_payload(5)
    assert payload["environment"] == {"temperature_C": 31.0, "humidity_pct": 45.0}
    assert payload["particulate_matter"] == {"PM1_0": 55.0, "PM2_5": 120.0, "PM10": 160.0}
    assert payload["gas_sensors"]["MQ2"] == {"raw_adc": 573, "voltage_V": 2.8}


@pytest.mark.asyncio
async def test_session_checks_server_and_supports_multiple_nodes():
    client = FakeClient()
    session = SimulationSession(
        SimulationConfig(node_ids=["sim-a", "sim-b"], samples=3, interval_seconds=0),
        client,
    )
    stats = await session.run()
    assert client.health_calls == 1
    assert client.ready_calls == 1
    assert stats.generated == 6
    assert stats.succeeded == 6
    assert {payload["node_id"] for payload in client.submissions} == {"sim-a", "sim-b"}


@pytest.mark.asyncio
async def test_session_stop_and_pause_resume():
    client = FakeClient()
    session = SimulationSession(SimulationConfig(samples=None, interval_seconds=0), client)
    session.pause()
    task = asyncio.create_task(session.run())
    await asyncio.sleep(0)
    assert not client.submissions
    session.resume()
    await asyncio.sleep(0)
    session.stop()
    stats = await task
    assert stats.generated >= 1
    assert stats.ended_at is not None


@pytest.mark.asyncio
async def test_error_policy_continue_and_stop():
    continue_session = SimulationSession(
        SimulationConfig(samples=3, interval_seconds=0, on_error="continue"), FakeClient(failures=1)
    )
    continue_stats = await continue_session.run()
    assert continue_stats.generated == 3
    assert continue_stats.failed == 1
    assert continue_stats.succeeded == 2

    stop_session = SimulationSession(
        SimulationConfig(samples=5, interval_seconds=0, on_error="stop"), FakeClient(failures=1)
    )
    stop_stats = await stop_session.run()
    assert stop_stats.generated == 1
    assert stop_stats.failed == 1


@pytest.mark.asyncio
async def test_server_unavailable_returns_session_result():
    stats = await SimulationSession(SimulationConfig(samples=1), UnavailableClient()).run()
    assert stats.generated == 0
    assert stats.failed == 1
    assert "health" in stats.errors[0]


def test_save_load_and_invalid_dataset(tmp_path: Path):
    generator = ScenarioGenerator("sim-node", seed=3, start_time=datetime(2026, 1, 1, tzinfo=timezone.utc))
    records = [generator.next_payload(300) for _ in range(3)]
    path = tmp_path / "dataset.jsonl"
    save_dataset(path, records)
    assert load_dataset(path) == records
    metadata = json.loads(path.with_suffix(".jsonl.meta.json").read_text())
    assert metadata["synthetic"] is True
    assert metadata["source_type"] == "hardware_simulator"

    invalid = tmp_path / "invalid.jsonl"
    invalid.write_text(json.dumps({"node_id": "bad"}) + "\n")
    with pytest.raises(ValueError):
        load_dataset(invalid)


@pytest.mark.asyncio
async def test_replay_uses_ingestion_client(tmp_path: Path):
    generator = ScenarioGenerator("sim-node", seed=4, start_time=datetime(2026, 1, 1, tzinfo=timezone.utc))
    path = tmp_path / "replay.jsonl"
    save_dataset(path, [generator.next_payload(300) for _ in range(4)])
    client = FakeClient()
    stats = await replay_dataset(path, client, accelerated=True)
    assert stats.succeeded == 4
    assert [record["timestamp"] for record in client.submissions] == [
        record["timestamp"] for record in load_dataset(path)
    ]


@pytest.mark.asyncio
async def test_replay_rebases_timestamps_without_changing_intervals(tmp_path: Path):
    generator = ScenarioGenerator("sim-node", seed=5, start_time=datetime(2020, 1, 1, tzinfo=timezone.utc))
    path = tmp_path / "old.jsonl"
    save_dataset(path, [generator.next_payload(300) for _ in range(3)])
    original = load_dataset(path)
    client = FakeClient()
    await replay_dataset(path, client, rebase_to_now=True)
    rebased = client.submissions
    original_gap = datetime.fromisoformat(original[1]["timestamp"]) - datetime.fromisoformat(original[0]["timestamp"])
    rebased_gap = datetime.fromisoformat(rebased[1]["timestamp"]) - datetime.fromisoformat(rebased[0]["timestamp"])
    assert rebased_gap == original_gap
    assert datetime.fromisoformat(rebased[-1]["timestamp"]) <= datetime.now(timezone.utc)
