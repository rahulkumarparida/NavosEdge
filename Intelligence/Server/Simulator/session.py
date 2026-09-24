"""Simulation sessions, dataset persistence, replay, and lifecycle controls."""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .client import ApiResult, IntelligenceClient
from .generator import ScenarioGenerator

logger = logging.getLogger(__name__)


@dataclass
class SimulationConfig:
    node_ids: list[str] = field(default_factory=lambda: ["sim-node-01"])
    scenario: str = "clean_background"
    interval_seconds: float = 5.0
    samples: int | None = 1
    server_url: str = "http://127.0.0.1:8420"
    seed: int = 42
    noise: float = 1.0
    timeout: float = 10.0
    on_error: str = "continue"
    send: bool = True
    save_path: Path | None = None
    custom: dict[str, float] = field(default_factory=dict)
    exact: dict[str, float] = field(default_factory=dict)
    verify: bool = False
    quiet: bool = False

    def __post_init__(self) -> None:
        if not self.node_ids:
            raise ValueError("At least one node ID is required")
        if self.interval_seconds < 0:
            raise ValueError("interval_seconds must be >= 0")
        if self.samples is not None and self.samples < 1:
            raise ValueError("samples must be >= 1 or None for continuous mode")
        if self.on_error not in {"continue", "stop"}:
            raise ValueError("on_error must be 'continue' or 'stop'")


@dataclass
class SessionStats:
    session_id: str
    scenario: str
    synthetic: bool = True
    started_at: str = ""
    ended_at: str | None = None
    generated: int = 0
    submitted: int = 0
    succeeded: int = 0
    failed: int = 0
    saved: int = 0
    errors: list[str] = field(default_factory=list)
    output_path: str | None = None


class SimulationSession:
    """A controllable multi-node simulation session."""

    def __init__(self, config: SimulationConfig, client: IntelligenceClient | None = None) -> None:
        self.config = config
        self.client = client or IntelligenceClient(config.server_url, config.timeout)
        self.stats = SessionStats(
            session_id=uuid.uuid4().hex[:12],
            scenario=config.scenario,
            started_at=datetime.now(timezone.utc).isoformat(),
        )
        self._stop_event = asyncio.Event()
        self._resume_event = asyncio.Event()
        self._resume_event.set()
        self._generators = {
            node_id: ScenarioGenerator(
                node_id=node_id,
                scenario=config.scenario,
                seed=config.seed + index,
                noise=config.noise,
                custom=config.custom,
                exact=config.exact,
            )
            for index, node_id in enumerate(config.node_ids)
        }
        self._saved_records: list[dict[str, Any]] = []
        self.last_responses: dict[str, dict[str, Any]] = {}

    def pause(self) -> None:
        self._resume_event.clear()
        logger.info("Simulation %s paused", self.stats.session_id)

    def resume(self) -> None:
        self._resume_event.set()
        logger.info("Simulation %s resumed", self.stats.session_id)

    def stop(self) -> None:
        self._stop_event.set()
        self._resume_event.set()
        logger.info("Stopping simulation %s", self.stats.session_id)

    async def run(self) -> SessionStats:
        """Run until the fixed count is reached or stop() is called."""
        try:
            if self.config.send:
                await self._check_server()
            sample_index = 0
            while not self._stop_event.is_set() and (self.config.samples is None or sample_index < self.config.samples):
                await self._resume_event.wait()
                if self._stop_event.is_set():
                    break
                await asyncio.gather(*(self._produce(node_id) for node_id in self._generators))
                sample_index += 1
                if self.config.samples is None or sample_index < self.config.samples:
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=self.config.interval_seconds)
                    except asyncio.TimeoutError:
                        pass
        except Exception as exc:
            self.stats.failed += 1
            self.stats.errors.append(str(exc))
            logger.error("Simulation %s could not start: %s", self.stats.session_id, exc)
        finally:
            self.stats.ended_at = datetime.now(timezone.utc).isoformat()
            if self.config.save_path is not None:
                self.stats.output_path = str(save_dataset(self.config.save_path, self._saved_records, self.stats))
            logger.info("Simulation complete: %s", json.dumps(asdict(self.stats), sort_keys=True))
        return self.stats

    async def _check_server(self) -> None:
        health = await self.client.health()
        ready = await self.client.ready()
        if not health.ok or not ready.ok:
            raise ConnectionError(f"Server checks failed: health={health.error or health.status_code}, ready={ready.error or ready.status_code}")
        if isinstance(ready.body, dict) and not ready.body.get("ready", False):
            raise ConnectionError(f"Server is not ready: {ready.body}")

    async def _produce(self, node_id: str) -> None:
        payload = self._generators[node_id].next_payload(self.config.interval_seconds)
        self.stats.generated += 1
        self._saved_records.append(payload)
        self.stats.saved += 1
        if not self.config.send:
            if not self.config.quiet:
                print(
                    f"[SIMULATED] node={node_id} timestamp={payload['timestamp']} "
                    f"PM2.5={payload['particulate_matter']['PM2_5']:.2f}"
                )
            return
        result = await self.client.submit(payload)
        self.stats.submitted += 1
        if result.ok and result.status_code in {200, 201, 202}:
            self.stats.succeeded += 1
            if isinstance(result.body, dict):
                self.last_responses[node_id] = result.body
            if not self.config.quiet:
                print(_format_feedback(node_id, result))
        else:
            self.stats.failed += 1
            message = f"{node_id}: {result.error or result.status_code}"
            self.stats.errors.append(message)
            logger.warning("Simulation request failed: %s", message)
            if not self.config.quiet:
                print(f"[FAILED] node={node_id} status={result.status_code} error={result.error or result.body}")
            if self.config.on_error == "stop":
                self.stop()
        logger.info("session=%s node=%s status=%s ok=%s", self.stats.session_id, node_id, result.status_code, result.ok)
        if self.config.verify and result.ok:
            status_result = await self.client.status(node_id)
            latest_result = await self.client.latest(node_id)
            if not self.config.quiet:
                print(
                    f"[VERIFY] node={node_id} status_http={status_result.status_code} "
                    f"latest_http={latest_result.status_code}"
                )


def _format_feedback(node_id: str, result: ApiResult) -> str:
    """Render the useful server response fields for terminal users."""
    body = result.body if isinstance(result.body, dict) else {}
    predictions = body.get("predictions", {})
    source = predictions.get("source", {})
    forecast = predictions.get("forecast", {})
    return (
        f"[ACCEPTED] node={node_id} http={result.status_code} "
        f"PM2.5={body.get('pm', {}).get('PM2_5', '-')} "
        f"source={source.get('value', '-')} "
        f"source_confidence={source.get('confidence', '-')} "
        f"forecast_confidence={forecast.get('confidence', '-')}"
    )


async def replay_dataset(
    path: Path,
    client: IntelligenceClient,
    *,
    accelerated: bool = True,
    interval_seconds: float = 0.0,
    on_error: str = "continue",
    rebase_to_now: bool = False,
) -> SessionStats:
    """Replay payload JSONL through the normal complete-reading endpoint."""
    records = load_dataset(path)
    if rebase_to_now and records:
        from datetime import datetime as _datetime
        newest = max(_datetime.fromisoformat(record["timestamp"]) for record in records)
        shift = datetime.now(timezone.utc) - newest.astimezone(timezone.utc)
        records = [
            {
                **record,
                "timestamp": (
                    _datetime.fromisoformat(record["timestamp"]).astimezone(timezone.utc) + shift
                ).isoformat(),
            }
            for record in records
        ]
    stats = SessionStats(session_id=uuid.uuid4().hex[:12], scenario="replay", started_at=datetime.now(timezone.utc).isoformat())
    previous: str | None = None
    try:
        for payload in records:
            if not accelerated and previous is not None:
                current = payload["timestamp"]
                from datetime import datetime as _datetime
                delay = max(0.0, (_datetime.fromisoformat(current) - _datetime.fromisoformat(previous)).total_seconds())
                await asyncio.sleep(delay)
            elif interval_seconds > 0:
                await asyncio.sleep(interval_seconds)
            previous = payload["timestamp"]
            stats.generated += 1
            result = await client.submit(payload)
            stats.submitted += 1
            if result.ok and result.status_code in {200, 201, 202}:
                stats.succeeded += 1
            else:
                stats.failed += 1
                stats.errors.append(f"{payload.get('node_id')}: {result.error or result.status_code}")
                if on_error == "stop":
                    break
    finally:
        stats.ended_at = datetime.now(timezone.utc).isoformat()
    return stats


def save_dataset(path: Path, records: Iterable[dict], stats: SessionStats | None = None) -> Path:
    """Save schema-valid payloads as JSONL plus a synthetic provenance sidecar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    records_list = list(records)
    with path.open("w", encoding="utf-8") as handle:
        for record in records_list:
            handle.write(json.dumps(record, separators=(",", ":")) + "\n")
    metadata = {
        "synthetic": True,
        "source_type": "hardware_simulator",
        "warning": "Synthetic test data; not physical measurements or model ground truth.",
        "records": len(records_list),
        "session": asdict(stats) if stats else None,
    }
    path.with_suffix(path.suffix + ".meta.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return path


def load_dataset(path: Path) -> list[dict]:
    """Load and validate payload JSONL; metadata is optional and external."""
    from app.schemas.sensor import SensorPayload
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
                SensorPayload.model_validate(record)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"Invalid dataset record at line {line_number}: {exc}") from exc
            records.append(record)
    return records


def install_stop_signal(session: SimulationSession) -> None:
    """Install Ctrl+C handling for a running CLI session."""
    def handler(_signum: int, _frame: Any) -> None:
        session.stop()
    signal.signal(signal.SIGINT, handler)
