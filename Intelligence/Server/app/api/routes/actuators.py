"""
FastAPI REST endpoints for Phase 3 ESP32 Wireless Actuator Management.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.emergency.auth import require_manager_auth
from app.emergency.actuator_schemas import (
    ActuatorDispatchRequest,
    ActuatorDispatchResult,
    ActuatorHeartbeatRequest,
)
from app.emergency.database import ForeignKeyViolationError, RecordNotFoundError
from app.emergency.schemas import ActuatorCommandResponse, ActuatorResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/actuators", tags=["actuators"])


@router.post(
    "/heartbeat",
    response_model=ActuatorResponse,
    status_code=status.HTTP_200_OK,
)
async def actuator_heartbeat(payload: ActuatorHeartbeatRequest, request: Request):
    """Register a NodeMCU ESP-32S V1.1 actuator or update its live heartbeat."""
    actuator_service = request.app.state.actuator_service
    try:
        return actuator_service.register_or_heartbeat(payload)
    except ForeignKeyViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Associated node '{payload.associated_node_id}' is not registered: {exc}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get("", response_model=List[ActuatorResponse])
async def list_actuators(request: Request, node_id: Optional[str] = None):
    """List registered actuators, optionally filtered by associated node_id."""
    emergency_db = request.app.state.emergency_db
    if node_id is not None:
        return emergency_db.list_actuators_for_node(node_id)
    results: List[ActuatorResponse] = []
    for node in emergency_db.list_nodes():
        results.extend(emergency_db.list_actuators_for_node(node.node_id))
    return results


@router.get("/{actuator_id}", response_model=ActuatorResponse)
async def get_actuator(actuator_id: str, request: Request):
    """Fetch current registration and state of an actuator."""
    emergency_db = request.app.state.emergency_db
    actuator = emergency_db.get_actuator(actuator_id)
    if actuator is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Actuator '{actuator_id}' not found",
        )
    return actuator


@router.get("/{actuator_id}/commands", response_model=List[ActuatorCommandResponse])
async def list_actuator_commands(actuator_id: str, request: Request):
    """Return command history for a given actuator."""
    emergency_db = request.app.state.emergency_db
    actuator = emergency_db.get_actuator(actuator_id)
    if actuator is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Actuator '{actuator_id}' not found",
        )
    return emergency_db.list_command_logs_for_actuator(actuator_id)


@router.post("/{actuator_id}/command", response_model=ActuatorDispatchResult)
async def dispatch_actuator_command(
    actuator_id: str,
    payload: ActuatorDispatchRequest,
    request: Request,
    _operator: str = Depends(require_manager_auth),
):
    """Dispatch a validated command (manual/demo or protection mode) to an ESP32."""
    actuator_service = request.app.state.actuator_service
    try:
        return await actuator_service.dispatch_command(
            actuator_id=actuator_id,
            command=payload.command,
            control_mode=payload.control_mode,
            event_id=payload.event_id,
            lease_seconds=payload.lease_seconds,
            reason=payload.reason,
        )
    except RecordNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

