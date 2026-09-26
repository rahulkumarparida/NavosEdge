import asyncio
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from Simulator.e2e import run_e2e


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_live_e2e_starts_server_and_completes_pipeline():
    server_dir = Path(__file__).resolve().parents[2]
    artifact_dir = server_dir / "artifacts"
    if not (artifact_dir / "gasnet.pt").exists():
        pytest.skip("Model artifacts are unavailable")

    with tempfile.TemporaryDirectory(prefix="navos_e2e_") as temp_dir:
        env = os.environ.copy()
        env.update({
            "NAVOS_PORT": "8421",
            "NAVOS_DATA_DIR": str(Path(temp_dir) / "data"),
            "NAVOS_ARTIFACTS_DIR": str(artifact_dir),
            "NAVOS_FORECAST_STORAGE_DIR": str(Path(temp_dir) / "forecast"),
            "NAVOS_LOG_LEVEL": "WARNING",
        })
        process = subprocess.Popen(
            [sys.executable, "-m", "app.main"],
            cwd=server_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            from Simulator.client import IntelligenceClient
            client = IntelligenceClient("http://127.0.0.1:8421", timeout=1.0)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                result = await client.ready()
                if result.ok and isinstance(result.body, dict) and result.body.get("ready"):
                    break
                await asyncio.sleep(0.25)
            else:
                output = process.stdout.read() if process.stdout else ""
                raise AssertionError(f"server did not become ready: {output[-2000:]}")

            class Args:
                server_url = "http://127.0.0.1:8421"
                node_id = "live-e2e-node"
                scenario = "traffic"
                count = 2
                duration = None
                interval = 0.0
                accelerated = True
                seed = 42
                noise = 1.0
                timeout = 5.0
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

            result = await run_e2e(Args())
            assert result["system"]["server_connected"] is True
            assert result["system"]["sse_connected"] is True
            assert result["system"]["processing_status"] == "completed"
            assert result["session"]["samples_sent"] == 2
            assert result["sensor_data"]["pm"]["PM2_5"] >= 0
            assert "status" in result["forecast"]
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
