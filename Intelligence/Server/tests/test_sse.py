"""
Tests for SSE event service internals and endpoint availability.
"""

import asyncio

import pytest

from app.services.events import EventService


@pytest.mark.asyncio
async def test_event_service_subscribe_yields_connected():
    """Verify that subscribing immediately yields a 'connected' event."""
    svc = EventService(heartbeat_interval=1.0)
    gen = svc.subscribe("node-01")

    # The first yielded value should be the connected event
    first = await gen.__anext__()
    assert "connected" in first

    # Clean up the generator
    await gen.aclose()


@pytest.mark.asyncio
async def test_event_service_publish_and_receive():
    """Published events are received by subscribers."""
    svc = EventService(heartbeat_interval=60.0)
    gen = svc.subscribe("node-01")

    # Consume the initial 'connected' event
    _ = await gen.__anext__()

    # Publish an event
    count = await svc.publish("node-01", "test_event", {"key": "value"})
    assert count == 1

    # Next yielded value should be our event
    event = await gen.__anext__()
    assert "test_event" in event
    assert "value" in event

    await gen.aclose()


@pytest.mark.asyncio
async def test_event_service_heartbeat():
    """After heartbeat_interval with no events, a heartbeat comment is yielded."""
    svc = EventService(heartbeat_interval=0.1)  # Very short for testing
    gen = svc.subscribe("node-01")

    _ = await gen.__anext__()  # 'connected'

    # Wait for heartbeat
    heartbeat = await asyncio.wait_for(gen.__anext__(), timeout=2.0)
    assert ":heartbeat" in heartbeat

    await gen.aclose()


@pytest.mark.asyncio
async def test_event_service_no_subscribers():
    """Publishing to a node with no subscribers returns 0."""
    svc = EventService()
    count = await svc.publish("nonexistent-node", "test", {})
    assert count == 0



