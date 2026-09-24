"""Command-line interface for the NavosEdge hardware simulator."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from .client import IntelligenceClient
from .generator import ScenarioGenerator, available_scenarios
from .session import SimulationConfig, SimulationSession, install_stop_signal, replay_dataset, save_dataset

logger = logging.getLogger("navos-simulator")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Synthetic NavosEdge hardware node simulator")
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list available scenarios")

    e2e = sub.add_parser("e2e", help="run the complete handshake, SSE, ingestion, and intelligence workflow")
    e2e.add_argument("--server-url", default="http://127.0.0.1:8420")
    e2e.add_argument("--node-id", default="e2e-node-01")
    e2e.add_argument("--scenario", choices=available_scenarios(), default="traffic")
    e2e.add_argument("--count", type=int, default=1)
    e2e.add_argument("--duration", type=float)
    e2e.add_argument("--interval", type=float, default=5.0)
    e2e.add_argument("--accelerated", action="store_true")
    e2e.add_argument("--json", action="store_true")

    sample = sub.add_parser("sample", help="generate one schema-valid sample")
    _add_generation_args(sample)
    sample.add_argument("--send", action="store_true", help="submit the sample to the server")

    start = sub.add_parser("start", help="run a fixed-count or continuous session")
    _add_generation_args(start)
    start.add_argument("--samples", type=int, default=1, help="samples per node; use 0 for continuous")
    start.add_argument("--send", action=argparse.BooleanOptionalAction, default=True)
    start.add_argument("--save", type=Path)
    start.add_argument("--on-error", choices=("continue", "stop"), default="continue")
    start.add_argument("--verify", action="store_true", help="query status/latest after accepted submissions")
    start.add_argument("--interactive", action="store_true", help="accept pause, resume, and stop commands from stdin")

    save = sub.add_parser("save", help="generate and save a local JSONL dataset")
    _add_generation_args(save)
    save.add_argument("--samples", type=int, default=12)
    save.add_argument("--output", type=Path, required=True)

    replay = sub.add_parser("replay", help="replay a JSONL dataset through the normal ingestion API")
    replay.add_argument("dataset", type=Path)
    replay.add_argument("--server-url", default="http://127.0.0.1:8420")
    replay.add_argument("--timeout", type=float, default=10.0)
    replay.add_argument("--real-time", action="store_true", help="honor timestamp gaps instead of accelerated replay")
    replay.add_argument("--interval", type=float, default=0.0, help="delay between requests in accelerated mode")
    replay.add_argument("--rebase-to-now", action="store_true", help="shift all timestamps together so the newest record is now")
    replay.add_argument("--on-error", choices=("continue", "stop"), default="continue")

    datasets = sub.add_parser("generate-datasets", help="create the checked-in reproducible fixture datasets")
    datasets.add_argument("--output-dir", type=Path, default=Path("test_data"))
    return parser


def _add_generation_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--node-id", action="append", dest="node_ids", default=None, help="node ID; repeat for multiple nodes")
    parser.add_argument("--scenario", "--classification", dest="scenario", choices=available_scenarios(), default="clean_background", help="synthetic classification/scenario profile")
    parser.add_argument("--interval", type=float, default=5.0, help="simulated seconds between samples")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--noise", type=float, default=1.0)
    parser.add_argument("--server-url", default="http://127.0.0.1:8420")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--custom", action="append", default=[], metavar="NAME=VALUE", help="custom scenario parameter; repeat as needed")
    parser.add_argument("--temperature", type=float, metavar="C", help="override temperature_C")
    parser.add_argument("--humidity", type=float, metavar="PCT", help="override humidity_pct")
    parser.add_argument("--pm1", type=float, metavar="VALUE", help="override PM1_0")
    parser.add_argument("--pm25", type=float, metavar="VALUE", help="override PM2_5")
    parser.add_argument("--pm10", type=float, metavar="VALUE", help="override PM10")
    parser.add_argument("--mq2", type=float, metavar="VOLTS", help="override MQ2 voltage_V")
    parser.add_argument("--mq9", type=float, metavar="VOLTS", help="override MQ9 voltage_V")
    parser.add_argument("--mq135", type=float, metavar="VOLTS", help="override MQ135 voltage_V")


def _config(args: argparse.Namespace, *, samples: int | None, send: bool, save_path: Path | None = None) -> SimulationConfig:
    return SimulationConfig(
        node_ids=args.node_ids or ["sim-node-01"],
        scenario=args.scenario,
        interval_seconds=args.interval,
        samples=samples,
        server_url=args.server_url,
        seed=args.seed,
        noise=args.noise,
        timeout=args.timeout,
        send=send,
        save_path=save_path,
        on_error=getattr(args, "on_error", "continue"),
        verify=getattr(args, "verify", False),
        custom=_custom_values(args),
        exact=_direct_values(args),
    )


def _parse_custom(values: list[str]) -> dict[str, float]:
    custom: dict[str, float] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Custom value must use NAME=VALUE: {value}")
        name, raw = value.split("=", 1)
        custom[name] = float(raw)
    return custom


def _custom_values(args: argparse.Namespace) -> dict[str, float]:
    custom = _parse_custom(args.custom)
    direct_values = {
        "temp": args.temperature,
        "humidity": args.humidity,
        "pm1": args.pm1,
        "pm25": args.pm25,
        "pm10": args.pm10,
        "mq2": args.mq2,
        "mq9": args.mq9,
        "mq135": args.mq135,
    }
    custom.update({name: value for name, value in direct_values.items() if value is not None})
    return custom


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


async def _run(args: argparse.Namespace) -> int:
    if args.command == "list":
        print("\n".join(available_scenarios()))
        return 0
    if args.command == "e2e":
        from .e2e import _main_async, build_parser
        e2e_args = build_parser().parse_args([])
        for name in ("server_url", "node_id", "scenario", "count", "duration", "interval", "accelerated", "json"):
            setattr(e2e_args, name, getattr(args, name))
        e2e_args.seed = 42
        e2e_args.noise = 1.0
        e2e_args.timeout = 10.0
        e2e_args.horizon = 60
        e2e_args.forecast_interval = 5
        e2e_args.custom = []
        for name in ("temperature", "humidity", "pm1", "pm25", "pm10", "mq2", "mq9", "mq135"):
            setattr(e2e_args, name, None)
        return await _main_async(e2e_args)
    if args.command == "sample":
        generator = ScenarioGenerator(
            args.node_ids[0] if args.node_ids else "sim-node-01",
            args.scenario,
            args.seed,
            args.noise,
            custom=_custom_values(args),
            exact=_direct_values(args),
        )
        payload = generator.next_payload(args.interval)
        if args.send:
            result = await IntelligenceClient(args.server_url, args.timeout).submit(payload)
            print(json.dumps({"payload": payload, "response": result.__dict__}, indent=2, default=str))
            return 0 if result.ok else 1
        print(json.dumps(payload, indent=2))
        return 0
    if args.command == "save":
        config = _config(args, samples=args.samples, send=False, save_path=args.output)
        session = SimulationSession(config)
        stats = await session.run()
        print(json.dumps(stats.__dict__, indent=2, default=str))
        return 0
    if args.command == "start":
        samples = None if args.samples == 0 else args.samples
        session = SimulationSession(_config(args, samples=samples, send=args.send, save_path=args.save))
        install_stop_signal(session)
        if args.interactive:
            stats = await _run_interactive(session)
        else:
            stats = await session.run()
        print(json.dumps(stats.__dict__, indent=2, default=str))
        return 0 if stats.failed == 0 else 1
    if args.command == "replay":
        client = IntelligenceClient(args.server_url, args.timeout)
        stats = await replay_dataset(
            args.dataset,
            client,
            accelerated=not args.real_time,
            interval_seconds=args.interval,
            on_error=args.on_error,
            rebase_to_now=args.rebase_to_now,
        )
        print(json.dumps(stats.__dict__, indent=2, default=str))
        return 0 if stats.failed == 0 else 1
    if args.command == "generate-datasets":
        generate_fixtures(args.output_dir)
        print(f"Generated synthetic fixtures in {args.output_dir}")
        return 0
    return 2


async def _run_interactive(session: SimulationSession):
    task = asyncio.create_task(session.run())
    print("Controls: pause, resume, stop")
    while not task.done():
        try:
            command = (await asyncio.to_thread(input, "sim> ")).strip().lower()
        except (EOFError, KeyboardInterrupt):
            session.stop()
            break
        if command == "pause":
            session.pause()
        elif command == "resume":
            session.resume()
        elif command == "stop":
            session.stop()
            break
        elif command:
            print("Use pause, resume, or stop")
    return await task


def generate_fixtures(output_dir: Path) -> None:
    """Create small deterministic payload datasets and validation fixtures."""
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = {
        "clean_background": 12,
        "traffic": 18,
        "heavy_dust": 18,
        "combustion": 18,
        "mixed_conditions": 18,
        "forecast_48h": 576,
    }
    for name, count in scenarios.items():
        scenario = "mixed_pollution" if name == "mixed_conditions" else ("clean_background" if name == "forecast_48h" else name)
        generator = ScenarioGenerator("fixture-node-01", scenario, seed=20260925, start_time=datetime(2026, 1, 1, tzinfo=timezone.utc))
        records = [generator.next_payload(5 * 60) for _ in range(count)]
        save_dataset(output_dir / f"{name}.jsonl", records)

    invalid = json.loads(json.dumps(ScenarioGenerator("fixture-node-01", seed=1, start_time=datetime(2026, 1, 1, tzinfo=timezone.utc)).next_payload()))
    invalid["environment"]["humidity_pct"] = 140
    save_dataset(output_dir / "invalid_payload.jsonl", [invalid])

    irregular_generator = ScenarioGenerator("fixture-node-01", "traffic", seed=20260925, start_time=datetime(2026, 1, 1, tzinfo=timezone.utc))
    irregular = []
    for index, gap in enumerate((0, 5, 20, 5, 45, 5)):
        payload = irregular_generator.next_payload(gap * 60 if index else 0)
        irregular.append(payload)
    save_dataset(output_dir / "timestamp_irregularities.jsonl", irregular)


def main() -> int:
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return asyncio.run(_run(args))
