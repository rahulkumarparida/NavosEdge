"""
Tests for the node list endpoint and multi-node behavior.
"""

import pytest
from tests.conftest import valid_sensor_payload


@pytest.mark.asyncio
async def test_list_nodes_empty(client):
    resp = await client.get("/api/v1/nodes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["nodes"] == []


@pytest.mark.asyncio
async def test_list_nodes_after_submissions(client):
    # Submit readings from two different nodes
    for nid in ("node-alpha", "node-beta"):
        payload = valid_sensor_payload(node_id=nid)
        await client.post(f"/api/v1/nodes/{nid}/readings", json=payload)

    resp = await client.get("/api/v1/nodes")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 2
    node_ids = {n["node_id"] for n in data["nodes"]}
    assert node_ids == {"node-alpha", "node-beta"}
