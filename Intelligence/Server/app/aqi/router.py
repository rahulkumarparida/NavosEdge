"""FastAPI routes for AQI calculation module."""

import logging
from typing import Optional

from fastapi import APIRouter, Query, Request

from app.aqi.schemas import LatestAQIResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["aqi"])


@router.get("/aqi/latest", response_model=LatestAQIResponse)
@router.get("/api/v1/aqi/latest", response_model=LatestAQIResponse)
async def get_latest_aqi(
    request: Request,
    node_id: Optional[str] = Query(default=None, description="Optional node_id filter"),
) -> LatestAQIResponse:
    """Return the most recently calculated AQI and relevant PM values."""
    aqi_service = getattr(request.app.state, "aqi_service", None)
    if aqi_service is None:
        return LatestAQIResponse(
            status="not_available",
            detail="AQI service is not initialized",
        )
    return aqi_service.get_latest(node_id=node_id)
