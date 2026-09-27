#!/usr/bin/env python3
"""
NavosEdge — UNO Q Resource Test

Measures runtime resource usage to verify UNO Q compatibility.
Works on both development machines and UNO Q (with /proc fallback).

Usage:
    python scripts/unoq_resource_test.py
"""

import gc
import json
import os
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "Intelligence" / "Server"))


def get_memory_mb():
    """Get current process RSS in MB. Uses psutil if available, falls back to /proc."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return process.memory_info().rss / (1024 * 1024)
    except ImportError:
        pass

    # Linux /proc fallback
    try:
        with open(f"/proc/{os.getpid()}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024  # KB -> MB
    except (FileNotFoundError, PermissionError):
        pass

    return -1.0


def get_cpu_times():
    """Get user+system CPU time in seconds."""
    try:
        import psutil
        process = psutil.Process(os.getpid())
        cpu = process.cpu_times()
        return cpu.user + cpu.system
    except ImportError:
        pass

    # /proc fallback
    try:
        with open(f"/proc/{os.getpid()}/stat") as f:
            parts = f.read().split()
            utime = int(parts[13]) / os.sysconf("SC_CLK_TCK")
            stime = int(parts[14]) / os.sysconf("SC_CLK_TCK")
            return utime + stime
    except (FileNotFoundError, PermissionError, IndexError):
        return -1.0


def get_disk_usage(path):
    """Get total size of a directory in MB."""
    total = 0
    p = Path(path)
    if p.is_file():
        return p.stat().st_size / (1024 * 1024)
    if p.is_dir():
        for f in p.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    return total / (1024 * 1024)


def test_startup():
    """Measure startup time and memory."""
    print("\n" + "=" * 60)
    print("TEST: Startup Time & Memory")
    print("=" * 60)

    gc.collect()
    mem_before = get_memory_mb()
    t0 = time.perf_counter()

    # Import core modules
    from app.core.config import get_settings
    from app.services.inference import TinyGasNetAdapter, TORCH_AVAILABLE

    settings = get_settings()

    t_import = time.perf_counter() - t0
    mem_after_import = get_memory_mb()

    print(f"  Import time:          {t_import * 1000:.1f} ms")
    print(f"  Memory before:        {mem_before:.1f} MB")
    print(f"  Memory after import:  {mem_after_import:.1f} MB")
    print(f"  Memory delta:         {mem_after_import - mem_before:.1f} MB")
    print(f"  TORCH_AVAILABLE:      {TORCH_AVAILABLE}")

    return {
        "import_time_ms": round(t_import * 1000, 1),
        "mem_before_mb": round(mem_before, 1),
        "mem_after_import_mb": round(mem_after_import, 1),
    }


def test_model_loading():
    """Measure model loading time and memory."""
    print("\n" + "=" * 60)
    print("TEST: Model Loading")
    print("=" * 60)

    from app.core.config import get_settings
    settings = get_settings()

    gc.collect()
    mem_before = get_memory_mb()
    t0 = time.perf_counter()

    # Try NumPy backend first
    try:
        from app.services.numpy_inference import NumpyGasNetAdapter
        adapter = NumpyGasNetAdapter(artifacts_dir=settings.ARTIFACTS_DIR)
        adapter.load()
        backend = "numpy"
    except (ImportError, Exception) as e:
        print(f"  NumPy backend unavailable ({e}), trying PyTorch...")
        from app.services.inference import TinyGasNetAdapter
        adapter = TinyGasNetAdapter(artifacts_dir=settings.ARTIFACTS_DIR)
        adapter.load()
        backend = "pytorch"

    t_load = time.perf_counter() - t0
    mem_after = get_memory_mb()

    print(f"  Backend:              {backend}")
    print(f"  Load time:            {t_load * 1000:.1f} ms")
    print(f"  Memory before:        {mem_before:.1f} MB")
    print(f"  Memory after:         {mem_after:.1f} MB")
    print(f"  Memory delta:         {mem_after - mem_before:.1f} MB")
    print(f"  Model loaded:         {adapter._loaded}")

    return {
        "backend": backend,
        "load_time_ms": round(t_load * 1000, 1),
        "mem_delta_mb": round(mem_after - mem_before, 1),
        "loaded": adapter._loaded,
    }


def test_inference_latency():
    """Measure single and repeated inference latency."""
    print("\n" + "=" * 60)
    print("TEST: Inference Latency")
    print("=" * 60)

    import asyncio
    from app.core.config import get_settings
    settings = get_settings()

    # Try NumPy backend
    try:
        from app.services.numpy_inference import NumpyGasNetAdapter
        adapter = NumpyGasNetAdapter(artifacts_dir=settings.ARTIFACTS_DIR)
        adapter.load()
        backend = "numpy"
    except (ImportError, Exception):
        from app.services.inference import TinyGasNetAdapter
        adapter = TinyGasNetAdapter(artifacts_dir=settings.ARTIFACTS_DIR)
        adapter.load()
        backend = "pytorch"

    if not adapter._loaded:
        print("  SKIPPED — model not loaded")
        return {"status": "skipped"}

    # Test inputs
    mq2, mq9, mq135, temp, hum = 1.5, 1.2, 1.8, 30.0, 55.0

    async def run_inference(n=1):
        results = []
        for _ in range(n):
            r = await adapter.predict(mq2, mq9, mq135, temp, hum)
            results.append(r)
        return results

    # Single inference
    t0 = time.perf_counter()
    results = asyncio.run(run_inference(1))
    t_single = (time.perf_counter() - t0) * 1000

    # Repeated inference (100 times)
    t0 = time.perf_counter()
    results = asyncio.run(run_inference(100))
    t_total = (time.perf_counter() - t0) * 1000
    t_avg = t_total / 100

    print(f"  Backend:              {backend}")
    print(f"  Single inference:     {t_single:.2f} ms")
    print(f"  100x average:         {t_avg:.2f} ms")
    print(f"  100x total:           {t_total:.1f} ms")
    if results:
        r = results[0]
        print(f"  Result status:        {r.status}")
        print(f"  Gas class:            {r.gas_class}")
        print(f"  Confidence:           {r.class_confidence}")

    return {
        "backend": backend,
        "single_ms": round(t_single, 2),
        "avg_100_ms": round(t_avg, 2),
        "total_100_ms": round(t_total, 1),
    }


def test_storage():
    """Measure storage consumed by artifacts and code."""
    print("\n" + "=" * 60)
    print("TEST: Storage Usage")
    print("=" * 60)

    artifacts = PROJECT_ROOT / "Intelligence" / "Server" / "artifacts"
    code = PROJECT_ROOT / "Intelligence" / "Server" / "app"
    data = PROJECT_ROOT / "Intelligence" / "Server" / "data"

    art_mb = get_disk_usage(artifacts)
    code_mb = get_disk_usage(code)
    data_mb = get_disk_usage(data)

    print(f"  Artifacts:            {art_mb:.2f} MB")
    print(f"  Application code:     {code_mb:.2f} MB")
    print(f"  Data directory:       {data_mb:.2f} MB")
    print(f"  Total:                {art_mb + code_mb + data_mb:.2f} MB")

    return {
        "artifacts_mb": round(art_mb, 2),
        "code_mb": round(code_mb, 2),
        "data_mb": round(data_mb, 2),
    }


def test_memory_stability():
    """Run repeated inferences and check for memory growth."""
    print("\n" + "=" * 60)
    print("TEST: Memory Stability (simulated 1-hour run)")
    print("=" * 60)

    import asyncio
    from app.core.config import get_settings
    settings = get_settings()

    try:
        from app.services.numpy_inference import NumpyGasNetAdapter
        adapter = NumpyGasNetAdapter(artifacts_dir=settings.ARTIFACTS_DIR)
        adapter.load()
    except (ImportError, Exception):
        from app.services.inference import TinyGasNetAdapter
        adapter = TinyGasNetAdapter(artifacts_dir=settings.ARTIFACTS_DIR)
        adapter.load()

    if not adapter._loaded:
        print("  SKIPPED — model not loaded")
        return {"status": "skipped"}

    # Simulate 360 inferences (1 per 10 seconds for 1 hour)
    n_iterations = 360
    gc.collect()
    mem_start = get_memory_mb()
    mem_samples = [mem_start]

    async def run_batch():
        for i in range(n_iterations):
            await adapter.predict(1.5, 1.2, 1.8, 30.0, 55.0)
            if (i + 1) % 60 == 0:
                gc.collect()
                mem_samples.append(get_memory_mb())

    t0 = time.perf_counter()
    asyncio.run(run_batch())
    elapsed = time.perf_counter() - t0

    gc.collect()
    mem_end = get_memory_mb()
    mem_samples.append(mem_end)

    growth = mem_end - mem_start
    print(f"  Iterations:           {n_iterations}")
    print(f"  Elapsed:              {elapsed:.1f}s")
    print(f"  Memory start:         {mem_start:.1f} MB")
    print(f"  Memory end:           {mem_end:.1f} MB")
    print(f"  Memory growth:        {growth:.1f} MB")
    print(f"  Leak suspected:       {'YES' if growth > 20 else 'NO'}")

    return {
        "iterations": n_iterations,
        "elapsed_s": round(elapsed, 1),
        "mem_start_mb": round(mem_start, 1),
        "mem_end_mb": round(mem_end, 1),
        "mem_growth_mb": round(growth, 1),
        "leak_suspected": growth > 20,
    }


def main():
    print("=" * 60)
    print("NavosEdge — UNO Q Resource Test")
    print("=" * 60)

    import platform
    print(f"  Platform:     {platform.machine()}")
    print(f"  Python:       {sys.version.split()[0]}")
    print(f"  PID:          {os.getpid()}")

    results = {}

    os.chdir(PROJECT_ROOT / "Intelligence" / "Server")

    results["startup"] = test_startup()
    results["model_loading"] = test_model_loading()
    results["inference"] = test_inference_latency()
    results["storage"] = test_storage()
    results["memory_stability"] = test_memory_stability()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(json.dumps(results, indent=2))

    # Write results to file
    output_path = PROJECT_ROOT / "docs" / "resource_test_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
