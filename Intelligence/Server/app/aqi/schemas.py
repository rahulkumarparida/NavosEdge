"""Schemas for AQI calculation results and API responses."""

from datetime import datetime
from typing import Dict, Optional
from pydantic import BaseModel, Field


class AQICalculationResult(BaseModel):
    """Result of an AQI calculation for a specific reading."""

    status: str = "available"
    aqi: float = Field(..., ge=0.0, description="Overall Air Quality Index")
    category: str = Field(..., description="AQI category string (e.g. Good, Moderate)")
    dominant_pollutant: str = Field(..., description="Pollutant responsible for maximum AQI sub-index")
    pm: Dict[str, float] = Field(..., description="Relevant PM values (PM1_0, PM2_5, PM10)")
    sub_indices: Dict[str, float] = Field(..., description="Individual sub-index for each PM parameter")
    timestamp: datetime = Field(..., description="Timestamp of the sensor reading")
    node_id: Optional[str] = Field(default=None, description="Identifier of the reporting node")


class LatestAQIResponse(BaseModel):
    """API response contract for GET /aqi/latest."""

    status: str = Field(..., description="'available' or 'not_available'")
    aqi: Optional[float] = Field(default=None, description="Most recently calculated AQI value")
    category: Optional[str] = Field(default=None, description="AQI qualitative category")
    dominant_pollutant: Optional[str] = Field(default=None, description="Dominant pollutant key")
    pm: Optional[Dict[str, float]] = Field(default=None, description="PM values corresponding to latest AQI")
    sub_indices: Optional[Dict[str, float]] = Field(default=None, description="PM sub-indices")
    timestamp: Optional[datetime] = Field(default=None, description="Timestamp of latest calculation")
    node_id: Optional[str] = Field(default=None, description="Node ID of latest calculation")
    detail: Optional[str] = Field(default=None, description="Detail message when not available")
