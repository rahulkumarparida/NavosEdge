"""
Manager Server API Router
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import List
from fastapi import APIRouter, HTTPException, Request, status
from starlette.responses import StreamingResponse

from app.models import (
    NodeRegistrationPayload,
    NodeState,
    NodeTelemetryPayload,
    OverviewResponse,
    SystemHealthResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=SystemHealthResponse)
@router.get("/api/v1/health", response_model=SystemHealthResponse)
async def health_check(request: Request):
    manager_service = request.app.state.manager_service
    overview = manager_service.get_overview()
    return SystemHealthResponse(
        status="healthy",
        version="1.0.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
        active_nodes=overview.active_nodes,
        inactive_nodes=overview.inactive_nodes,
        total_nodes=overview.total_nodes,
    )


@router.get("/overview", response_model=OverviewResponse)
@router.get("/api/v1/overview", response_model=OverviewResponse)
async def get_overview(request: Request):
    manager_service = request.app.state.manager_service
    return manager_service.get_overview()


@router.get("/nodes", response_model=List[NodeState])
@router.get("/api/v1/nodes", response_model=List[NodeState])
async def list_nodes(request: Request):
    manager_service = request.app.state.manager_service
    return manager_service.list_nodes()


@router.get("/nodes/{node_id}", response_model=NodeState)
@router.get("/api/v1/nodes/{node_id}", response_model=NodeState)
async def get_node(node_id: str, request: Request):
    manager_service = request.app.state.manager_service
    node = manager_service.get_node(node_id)
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node '{node_id}' not found",
        )
    return node


@router.post("/api/v1/nodes/register", response_model=NodeState)
async def register_node(payload: NodeRegistrationPayload, request: Request):
    manager_service = request.app.state.manager_service
    return await manager_service.register_node(payload.node_id, payload.location)


@router.post("/api/v1/nodes/{node_id}/telemetry", response_model=NodeState)
@router.post("/nodes/{node_id}/telemetry", response_model=NodeState)
async def ingest_telemetry(node_id: str, payload: NodeTelemetryPayload, request: Request):
    if payload.node_id and payload.node_id != node_id:
        payload.node_id = node_id
    elif not payload.node_id:
        payload.node_id = node_id

    manager_service = request.app.state.manager_service
    return await manager_service.ingest_telemetry(payload)


@router.get("/stream")
@router.get("/api/v1/stream")
async def sse_stream(request: Request):
    manager_service = request.app.state.manager_service
    queue = await manager_service.subscribe()

    async def event_generator():
        try:
            # Send initial state snapshot on connection
            init_overview = manager_service.get_overview()
            yield f"event: overview\ndata: {init_overview.model_dump_json()}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=10.0)
                    yield msg
                except asyncio.TimeoutError:
                    # Heartbeat
                    yield f"event: heartbeat\ndata: {json.dumps({'time': datetime.now(timezone.utc).isoformat()})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await manager_service.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
