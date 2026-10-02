"""
Hardware data & control router for NavosEdge Intelligence Server.
"""

import asyncio
import json
import logging
from fastapi import APIRouter, Request, status
from starlette.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.schemas.sensor import SensorPayload
from app.schemas.intelligence import IntelligenceResult

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/hardware",
    tags=["hardware"],
)


class ControlConfigPayload(BaseModel):
    node_id: str = Field(..., min_length=1)
    sampling_interval: int = Field(..., gt=0)


class HardwareReadyPayload(BaseModel):
    node_id: str = Field(..., min_length=1)
    status: str = Field(default="READY")
    warmup_duration_s: float = Field(default=30.0)


@router.post(
    "/data",
    response_model=IntelligenceResult,
    status_code=status.HTTP_201_CREATED,
    summary="Submit hardware sensor data",
)
async def submit_hardware_data(payload: SensorPayload, request: Request):
    """
    Hardware data route for C++ client.
    Accepts SensorPayload and delegates to the processing pipeline.
    """
    logger.debug("Received hardware data from node_id=%s", payload.node_id)
    processing_service = request.app.state.processing_service
    result = await processing_service.process_reading(payload)
    return result


@router.post(
    "/ready",
    summary="Receive READY signal from hardware node after sensor warm-up",
)
async def hardware_ready(payload: HardwareReadyPayload, request: Request):
    """
    Called by C++ Hardware node after completing its 30-second sensor warm-up.
    Registers node as ready and triggers data acquisition over SSE.
    """
    from datetime import datetime, timezone
    logger.info(
        "Hardware node %s sensors READY after %.1fs warm-up period",
        payload.node_id,
        payload.warmup_duration_s,
    )
    event_service = request.app.state.event_service
    node_registry = request.app.state.node_registry
    node_registry.register_reading(payload.node_id, datetime.now(timezone.utc))

    # Send immediate data request trigger over SSE control channel
    sub_count = await event_service.publish(
        payload.node_id,
        "request_data",
        {"trigger": "handshake_ready", "cycle_interval_s": 60},
    )
    return {
        "status": "ACK",
        "node_id": payload.node_id,
        "ready": True,
        "sse_subscribers_notified": sub_count,
    }



@router.get(
    "/events",
    summary="SSE control channel for hardware nodes",
)
async def hardware_events(request: Request, node_id: str = "uno-q-001"):
    """
    Persistent SSE control channel for hardware node.
    Sends connected event, periodic heartbeats, and server-published control events.
    """
    event_service = request.app.state.event_service

    async def event_generator():
        logger.info("Hardware node %s connected to SSE control channel", node_id)
        # 1. Initial connection event
        init_evt = f"event: connected\ndata: {json.dumps({'node_id': node_id})}\n\n"
        yield init_evt

        queue: asyncio.Queue = asyncio.Queue()
        async with event_service._lock:
            if node_id not in event_service._subscribers:
                event_service._subscribers[node_id] = []
            event_service._subscribers[node_id].append(queue)

        try:
            while True:
                if await request.is_disconnected():
                    logger.info("Hardware node %s disconnected from SSE", node_id)
                    break
                try:
                    event_str = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield event_str
                except asyncio.TimeoutError:
                    yield f"event: heartbeat\ndata: {json.dumps({'status': 'alive'})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await event_service.disconnect(node_id, queue)
            logger.info("Cleaned up SSE subscription for node %s", node_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/config",
    summary="Publish configuration update event to hardware node",
)
async def update_hardware_config(payload: ControlConfigPayload, request: Request):
    """
    Publishes a config update event to a connected hardware node via SSE.
    """
    event_service = request.app.state.event_service
    count = await event_service.publish(
        payload.node_id,
        "config",
        {"sampling_interval": payload.sampling_interval},
    )
    return {
        "status": "published" if count > 0 else "no_subscriber",
        "node_id": payload.node_id,
        "subscribers_notified": count,
        "sampling_interval": payload.sampling_interval,
    }
