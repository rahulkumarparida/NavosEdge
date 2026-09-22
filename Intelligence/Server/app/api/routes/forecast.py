"""
Forecast API routes — Phase 4 lightweight autoregressive forecast plugin.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.schemas.forecast import (
    CleanupResponse,
    ForecastHistoryResponse,
    ForecastReadingAccepted,
    ForecastReadingInput,
    ForecastResponse,
    SyntheticGeneratorConfig,
    SyntheticGeneratorResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/forecast", tags=["forecast"])


def _get_plugin(request: Request):
    """Retrieve the forecast plugin from app state."""
    plugin = getattr(request.app.state, "forecast_plugin", None)
    if plugin is None or not plugin.is_initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Forecast plugin is not initialized.",
        )
    return plugin


# ------------------------------------------------------------------ #
#  Ingest                                                              #
# ------------------------------------------------------------------ #


@router.post(
    "/nodes/{node_id}/readings",
    response_model=ForecastReadingAccepted,
    status_code=status.HTTP_201_CREATED,
)
async def submit_forecast_reading(
    node_id: str, reading: ForecastReadingInput, request: Request
):
    """Submit a PM reading to the forecast plugin's rolling store."""
    if node_id != reading.node_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="node_id in URL does not match payload node_id.",
        )
    plugin = _get_plugin(request)
    return await plugin.async_ingest(reading)


# ------------------------------------------------------------------ #
#  Forecast                                                            #
# ------------------------------------------------------------------ #


@router.get(
    "/nodes/{node_id}/predict",
    response_model=ForecastResponse,
)
async def get_forecast(
    node_id: str,
    request: Request,
    horizon_minutes: Optional[int] = Query(
        default=None, ge=5, le=1440, description="Forecast horizon in minutes"
    ),
    sampling_interval_minutes: Optional[int] = Query(
        default=None, ge=1, le=60, description="Sampling interval in minutes"
    ),
):
    """Request a PM forecast for a node."""
    plugin = _get_plugin(request)
    return await plugin.async_forecast(
        node_id=node_id,
        horizon_minutes=horizon_minutes,
        sampling_interval_minutes=sampling_interval_minutes,
    )


# ------------------------------------------------------------------ #
#  History / status                                                    #
# ------------------------------------------------------------------ #


@router.get(
    "/nodes/{node_id}/history",
    response_model=ForecastHistoryResponse,
)
async def get_forecast_history(node_id: str, request: Request):
    """View the forecast plugin's retained history/status for a node."""
    plugin = _get_plugin(request)
    return await plugin.async_get_history(node_id)


# ------------------------------------------------------------------ #
#  Cleanup                                                             #
# ------------------------------------------------------------------ #


@router.post(
    "/cleanup",
    response_model=CleanupResponse,
)
async def trigger_cleanup(
    request: Request,
    node_id: Optional[str] = Query(
        default=None, description="Limit cleanup to a specific node"
    ),
):
    """Trigger expired-data cleanup for the forecast store."""
    plugin = _get_plugin(request)
    return await plugin.async_delete_expired(node_id)


# ------------------------------------------------------------------ #
#  Synthetic data                                                      #
# ------------------------------------------------------------------ #


@router.post(
    "/synthetic/generate",
    response_model=SyntheticGeneratorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def generate_synthetic_data(
    config: SyntheticGeneratorConfig, request: Request
):
    """Generate synthetic PM data and replay it through the forecast plugin."""
    plugin = _get_plugin(request)

    from app.forecast.generator import generate_synthetic_series, replay_through_plugin

    readings = generate_synthetic_series(config)
    ingested = replay_through_plugin(readings, plugin)

    seed_used = config.seed if config.seed is not None else 42

    return SyntheticGeneratorResponse(
        node_id=config.node_id,
        records_generated=ingested,
        duration_hours=config.duration_hours,
        sampling_interval_minutes=config.sampling_interval_minutes,
        seed_used=seed_used,
        message=(
            f"Generated and ingested {ingested} synthetic records "
            f"for node '{config.node_id}'."
        ),
    )
