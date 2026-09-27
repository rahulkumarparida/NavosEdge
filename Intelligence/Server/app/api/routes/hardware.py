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
