"""
Node API routes — readings submission, status, latest, events (SSE), list.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, status
from starlette.responses import StreamingResponse

from app.schemas.sensor import SensorPayload
from app.schemas.source_classification import SourceClassificationResult
from app.schemas.responses import (
    LatestReadingResponse,
    NodeInfo,
    NodeListResponse,
    NodeStatusResponse,
    ReadingAccepted,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/api/v1/nodes/{node_id}/readings",
    response_model=ReadingAccepted,
    status_code=status.HTTP_201_CREATED,
)
async def submit_reading(node_id: str, payload: SensorPayload, request: Request):
    if node_id != payload.node_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="node_id in URL does not match payload node_id",
        )
    processing_service = request.app.state.processing_service
    result = await processing_service.process_reading(payload)
    return result


@router.get("/api/v1/nodes/{node_id}/status", response_model=NodeStatusResponse)
async def get_node_status(node_id: str, request: Request):
    node_registry = request.app.state.node_registry
    inference_adapter = request.app.state.inference_adapter
    source_classifier = request.app.state.source_classifier

    node = node_registry.get_node(node_id)
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Node not found"
        )

    return NodeStatusResponse(
        node_id=node.node_id,
        status=node.status,
        last_reading_at=node.last_seen,
        total_readings=node.total_readings,
        inference_available=getattr(inference_adapter, "_loaded", False),
        source_classifier_available=getattr(source_classifier, "_loaded", False),
    )


@router.get("/api/v1/nodes/{node_id}/latest", response_model=LatestReadingResponse)
async def get_latest_reading(node_id: str, request: Request):
    storage = request.app.state.storage
    node_registry = request.app.state.node_registry

    if not node_registry.has_node(node_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Node not found"
        )

    record = await storage.get_latest_reading(node_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No readings stored for this node",
        )

    inference_data = record.get("inference")

    return LatestReadingResponse(
        node_id=node_id,
        reading=record,
        inference=inference_data,
        recorded_at=record.get("timestamp", datetime.now(timezone.utc).isoformat()),
    )


@router.get("/api/v1/nodes/{node_id}/events")
async def node_events(node_id: str, request: Request):
    event_service = request.app.state.event_service

    async def event_generator():
        async for event in event_service.subscribe(node_id):
            if await request.is_disconnected():
                break
            yield event

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/v1/nodes", response_model=NodeListResponse)
async def list_nodes(request: Request):
    node_registry = request.app.state.node_registry
    nodes_data = node_registry.list_nodes()
    nodes = [
        NodeInfo(
            node_id=n.node_id,
            first_seen=n.first_seen,
            last_seen=n.last_seen,
            total_readings=n.total_readings,
            status=n.status,
        )
        for n in nodes_data
    ]
    return NodeListResponse(nodes=nodes, count=len(nodes))
