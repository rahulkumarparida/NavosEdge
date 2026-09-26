import asyncio
from datetime import datetime, timezone

import pytest

from Simulator.client import ApiResult
from Simulator.e2e import run_e2e


class FakeE2EClient:
    def __init__(self):
        self.submitted = []

    async def health(self):
        return ApiResult(True, 200, {"status": "ok"})

    async def ready(self):
        return ApiResult(True, 200, {"ready": True})

    async def submit(self, payload):
        self.submitted.append(payload)
        return ApiResult(
            True,
            201,
            {
                "aqi": None,
                "pm": payload["particulate_matter"],
                "temperature_C": payload["environment"]["temperature_C"],
                "humidity_pct": payload["environment"]["humidity_pct"],
                "predictions": {
                    "source": {"value": "TRAFFIC", "confidence": 0.8},
                    "forecast": {"value": {"status": "insufficient_history", "PM1_0": [], "PM2_5": [], "PM10": []}, "confidence": 0.0},
                },
            },
        )

    async def latest(self, node_id):
        payload = self.submitted[-1]
        return ApiResult(True, 200, {"reading": {
            "node_id": node_id,
            "timestamp": payload["timestamp"],
            "environment": payload["environment"],
            "pipeline": {
                "health": {"status": "ok", "issues": []},
                "advisory": {"level": "NORMAL", "messages": []},
                "source_classification": {"top_source": "TRAFFIC", "predictions": [], "uncertainty": {}},
            },
        }, "inference": {"status": "success"}})

    async def forecast(self, node_id, horizon_minutes, sampling_interval_minutes):
        return ApiResult(True, 200, {"status": "insufficient_history", "channels": [], "history_points_used": 1})


class Args:
    server_url = "http://testserver"
    node_id = "e2e-node"
    scenario = "traffic"
    count = 2
    duration = None
    interval = 0.0
    accelerated = True
    seed = 42
    noise = 1.0
    timeout = 1.0
    horizon = 60
    forecast_interval = 5
    custom = []
    temperature = None
    humidity = None
    pm1 = None
    pm25 = None
    pm10 = None
    mq2 = None
    mq9 = None
    mq135 = None


@pytest.mark.asyncio
async def test_e2e_result_contains_pipeline_sections(monkeypatch):
    client = FakeE2EClient()
    monkeypatch.setattr("Simulator.e2e.IntelligenceClient", lambda *args, **kwargs: client)

    async def fake_sse(self):
        self.connected.set()
        await self._stop.wait()

    monkeypatch.setattr("Simulator.e2e.SseCollector.run", fake_sse)
    result = await run_e2e(Args())

    assert result["session"]["data_source"] == "synthetic"
    assert result["session"]["samples_sent"] == 2
    assert result["system"]["server_connected"] is True
    assert result["system"]["sse_connected"] is True
    assert result["system"]["processing_status"] == "completed"
    assert result["source_classification"]["value"] == "TRAFFIC"
    assert result["sensor_data"]["predictions"]["source"]["value"] == "TRAFFIC"
    assert result["forecast"]["status"] == "insufficient_history"
    assert len(client.submitted) == 2
