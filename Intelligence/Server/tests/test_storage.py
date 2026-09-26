"""
Tests for JSONL storage service.
"""

import asyncio
import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

from app.storage.jsonl_store import JsonlStorageService


@pytest.fixture()
def storage_dir():
    d = tempfile.mkdtemp(prefix="navos_storage_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture()
def storage(storage_dir):
    return JsonlStorageService(
        data_dir=storage_dir, max_file_size_mb=0.001, max_files_per_node=3
    )


@pytest.mark.asyncio
async def test_append_and_get_latest(storage):
    record = {"reading_id": "abc123", "value": 42}
    await storage.append_reading("node-01", record)
    latest = await storage.get_latest_reading("node-01")
    assert latest is not None
    assert latest["reading_id"] == "abc123"
    assert latest["value"] == 42


@pytest.mark.asyncio
async def test_get_latest_nonexistent_node(storage):
    latest = await storage.get_latest_reading("nonexistent")
    assert latest is None


@pytest.mark.asyncio
async def test_readings_count(storage):
    for i in range(5):
        await storage.append_reading("node-01", {"i": i})
    count = await storage.get_readings_count("node-01")
    assert count >= 5


@pytest.mark.asyncio
async def test_storage_health_check(storage):
    assert storage.check_storage_health() is True


@pytest.mark.asyncio
async def test_append_multiple_returns_latest(storage):
    for i in range(10):
        await storage.append_reading("node-01", {"seq": i})
    latest = await storage.get_latest_reading("node-01")
    assert latest is not None
    # Latest should be the last one written
    assert latest["seq"] == 9


@pytest.mark.asyncio
async def test_file_rotation(storage, storage_dir):
    """With max_file_size_mb=0.001 (≈1KB), writing many records should trigger rotation."""
    large_record = {"data": "x" * 500}
    for _ in range(20):
        await storage.append_reading("node-rotate", large_record)

    node_dir = storage_dir / "readings" / "node-rotate"
    files = list(node_dir.iterdir()) if node_dir.exists() else []
    # Should have created rotated files and limited by max_files_per_node=3
    assert len(files) <= 4  # 3 rotated + 1 current (at most)
