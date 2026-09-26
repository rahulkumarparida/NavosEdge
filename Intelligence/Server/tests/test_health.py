"""
Tests for health and readiness endpoints.
"""

import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_readiness_returns_status(client):
    resp = await client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert "ready" in data
    assert "storage_ok" in data
    assert "model_loaded" in data
    assert "timestamp" in data
    # Without model artifacts, model_loaded should be False
    assert data["model_loaded"] is False
    # Storage should be ok since we created a temp dir
    assert data["storage_ok"] is True
