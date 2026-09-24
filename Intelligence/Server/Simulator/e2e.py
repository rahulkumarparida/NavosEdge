"""Phase 6 single-command end-to-end simulator workflow."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

from .client import IntelligenceClient
from .generator import available_scenarios
from .session import SimulationConfig, SimulationSession

logger = logging.getLogger("navos-e2e")


class E2EError(RuntimeError):
    """Raised when the end-to-end lifecycle cannot complete."""


class SseCollector:
    def __init__(self, base_url: str, node_id: str, timeout: float) -> None:
        self.url = f"{base_url.rstrip('/')}/api/v1/nodes/{node_id}/events"
        self.timeout = timeout
        self.connected = asyncio.Event()
        self.events: list[dict[str, Any]] = []
        self.error: str | None = None
        self._stop = asyncio.Event()

    async def run(self) -> None:
        try:
            timeout = httpx.Timeout(None, connect=self.timeout)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("GET", self.url, headers={"Accept": "text/event-stream"}) as response:
                    if response.status_code != 200:
                        raise E2EError(f"SSE connection returned HTTP {response.status_code}")
                    event_name = "message"
                    data_lines: list[str] = []
                    async for line in response.aiter_lines():
                        if self._stop.is_set():
                            break
                        if line.startswith("event:"):
                            event_name = line[6:].strip()
                        elif line.startswith("data:"):
                            data_lines.append(line[5:].strip())
                        elif line == "" and data_lines:
                            raw = "".join(data_lines)
                            data_lines = []
                            try:
                                data = json.loads(raw)
                            except json.JSONDecodeError:
                                data = {"raw": raw}
                            event = {"event": event_name, "data": data}
                            self.events.append(event)
                            if event_name == "connected":
                                self.connected.set()
                            event_name = "message"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.error = str(exc)
            if not self.connected.is_set():
                self.connected.set()

    async def stop(self) -> None:
        self._stop.set()


async def run_e2e(args: argparse.Namespace) -> dict[str, Any]:
    session_id = uuid.uuid4().hex[:12]
    node_id = args.node_id
    client = IntelligenceClient(args.server_url, args.timeout)
    started_at = datetime.now(timezone.utc).isoformat()

    health = await client.health()
    ready = await client.ready()
    if not health.ok:
        raise E2EError(f"server unavailable during health check: {health.error or health.status_code}")
    if not ready.ok:
        raise E2EError(f"server unavailable during readiness check: {ready.error or ready.status_code}")
    if not isinstance(ready.body, dict) or not ready.body.get("ready", False):
        raise E2EError(f"readiness failure: {ready.body}")

    sse = SseCollector(getattr(client, "base_url", args.server_url), node_id, args.timeout)
    sse_task = asyncio.create_task(sse.run())
    try:
        try:
            await asyncio.wait_for(sse.connected.wait(), timeout=args.timeout)
        except asyncio.TimeoutError as exc:
            raise E2EError(f"SSE timeout: {sse.error or 'connection confirmation not received'}") from exc
        if sse.error:
            raise E2EError(f"SSE failure: {sse.error}")

        samples = args.count
        if args.duration is not None:
            samples = max(1, int(args.duration / max(args.interval, 0.001)))
        if samples < 1:
            raise E2EError("count or duration must produce at least one reading")

        config = SimulationConfig(
            node_ids=[node_id],
            scenario=args.scenario,
            interval_seconds=0.0 if args.accelerated else args.interval,
            samples=samples,
            server_url=args.server_url,
            seed=args.seed,
            noise=args.noise,
            timeout=args.timeout,
            send=True,
            exact=_direct_values(args),
            custom=_parse_custom(args.custom),
            on_error="stop",
            quiet=getattr(args, "json", False),
        )
        session = SimulationSession(config, client)
        stats = await session.run()
        if stats.succeeded == 0:
            raise E2EError(f"sensor transmission failed: {stats.errors}")

        latest = await client.latest(node_id)
        if not latest.ok:
            raise E2EError(f"final latest result failed: HTTP {latest.status_code} {latest.error or ''}".strip())
        forecast = await client.forecast(node_id, args.horizon, args.forecast_interval)
        await asyncio.sleep(0)

        latest_body = latest.body if isinstance(latest.body, dict) else {}
        response_body = session.last_responses.get(node_id, {})
        reading = response_body or latest_body.get("reading", latest_body)
        predictions = reading.get("predictions", {}) if isinstance(reading, dict) else {}
        source = predictions.get("source", {})
        forecast_body = forecast.body if isinstance(forecast.body, dict) else {}
        raw_status = forecast_body.get("status") if isinstance(forecast_body, dict) else None
        if raw_status == "insufficient_data":
            forecast_result = {**forecast_body, "status": "insufficient_history"}
        elif forecast.status_code == 200:
            forecast_result = forecast_body
        elif forecast.status_code == 503:
            forecast_result = {"status": "unavailable", "error": forecast.error or forecast_body}
        else:
            forecast_result = {
                **(forecast_body if isinstance(forecast_body, dict) else {}),
                "status": "insufficient_history" if raw_status == "insufficient_data" else (raw_status or "error"),
            }

        return {
            "session": {
                "id": session_id,
                "node_id": node_id,
                "scenario": args.scenario,
                "data_source": "synthetic",
                "started_at": started_at,
                "ended_at": datetime.now(timezone.utc).isoformat(),
                "samples_sent": stats.succeeded,
            },
            "sensor_data": reading,
            "source_classification": source,
            "forecast": forecast_result,
            "advisory": reading.get("advisory", {}) if isinstance(reading, dict) else {},
            "system": {
                "server_connected": True,
                "ready": True,
                "sse_connected": sse.connected.is_set() and sse.error is None,
                "sse_events_received": len(sse.events),
                "processing_status": "completed",
            },
        }
    finally:
        await sse.stop()
        sse_task.cancel()
        try:
            await sse_task
        except asyncio.CancelledError:
            pass


def _parse_custom(values: list[str]) -> dict[str, float]:
    result: dict[str, float] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"custom value must use NAME=VALUE: {value}")
        name, raw = value.split("=", 1)
        result[name] = float(raw)
    return result


def _direct_values(args: argparse.Namespace) -> dict[str, float]:
    return {
        name: value
        for name, value in {
            "temp": args.temperature,
            "humidity": args.humidity,
            "pm1": args.pm1,
            "pm25": args.pm25,
            "pm10": args.pm10,
            "mq2": args.mq2,
            "mq9": args.mq9,
            "mq135": args.mq135,
        }.items()
        if value is not None
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the complete NavosEdge synthetic hardware workflow")
    parser.add_argument("--server-url", default="http://127.0.0.1:8420")
    parser.add_argument("--node-id", default="e2e-node-01")
    parser.add_argument("--scenario", choices=available_scenarios(), default="traffic")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--duration", type=float, help="session duration in simulated seconds")
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--accelerated", action="store_true", help="send without waiting between readings")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--noise", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--horizon", type=int, default=60)
    parser.add_argument("--forecast-interval", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="print only the final JSON result")
    parser.add_argument("--custom", action="append", default=[], metavar="NAME=VALUE")
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--humidity", type=float)
    parser.add_argument("--pm1", type=float)
    parser.add_argument("--pm25", type=float)
    parser.add_argument("--pm10", type=float)
    parser.add_argument("--mq2", type=float)
    parser.add_argument("--mq9", type=float)
    parser.add_argument("--mq135", type=float)
    return parser


async def _main_async(args: argparse.Namespace) -> int:
    try:
        result = await run_e2e(args)
    except Exception as exc:
        failure = {
            "session": {"node_id": args.node_id, "data_source": "synthetic"},
            "system": {"server_connected": False, "sse_connected": False, "processing_status": "failed"},
            "error": str(exc),
        }
        print(json.dumps(failure, indent=None if args.json else 2, sort_keys=True))
        return 1
    print(json.dumps(result, indent=None if args.json else 2, sort_keys=True))
    return 0


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")
    return asyncio.run(_main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
