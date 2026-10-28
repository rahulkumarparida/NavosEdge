"""Schemas for AQI calculation results and API responses."""

from datetime import datetime
from typing import Dict, Optional
from pydantic import BaseModel, Field


class AQICalculationResult(BaseModel):
    """Result of an AQI calculation for a specific reading or moving window."""

    status: str = "available"
    aqi: Optional[float] = Field(default=None, ge=0.0, description="Overall Air Quality Index")
    category: str = Field(..., description="AQI category string (e.g. Good, Satisfactory, Moderate)")
    dominant_pollutant: str = Field(..., description="Pollutant responsible for maximum AQI sub-index")
    pm: Dict[str, float] = Field(..., description="Relevant PM values (PM1_0, PM2_5, PM10)")
    sub_indices: Dict[str, float] = Field(..., description="Individual regulatory sub-indices")
    timestamp: datetime = Field(..., description="Timestamp of the sensor reading")
    node_id: Optional[str] = Field(default=None, description="Identifier of the reporting node")
    data_sufficiency: str = Field(default="VALID", description="Sufficiency status: VALID, INSUFFICIENT_DATA, or INVALID_INPUT")
    is_complete_national_aqi: bool = Field(default=False, description="True only if all criteria regulatory pollutants are verified")
    calculation_method: str = Field(default="CPCB_PM_ESTIMATE", description="Calculation methodology identifier")
    averaging_window_hours: float = Field(default=24.0, description="Averaging window duration in hours")
    data_coverage_hours: float = Field(default=0.0, description="Count of valid hourly buckets represented in the 24-hour window")
    is_provisional: bool = Field(default=False, description="True if estimate is provisional due to incomplete window")


class LatestAQIResponse(BaseModel):
    """API response contract for GET /aqi/latest."""

    status: str = Field(..., description="'available', 'not_available', 'VALID', 'INSUFFICIENT_DATA', or 'INVALID_INPUT'")
    aqi: Optional[float] = Field(default=None, description="Most recently calculated AQI value")
    category: Optional[str] = Field(default=None, description="AQI qualitative category")
    dominant_pollutant: Optional[str] = Field(default=None, description="Dominant pollutant key")
    pm: Optional[Dict[str, float]] = Field(default=None, description="PM values corresponding to latest AQI")
    sub_indices: Optional[Dict[str, float]] = Field(default=None, description="PM sub-indices")
    timestamp: Optional[datetime] = Field(default=None, description="Timestamp of latest calculation")
    node_id: Optional[str] = Field(default=None, description="Node ID of latest calculation")
    detail: Optional[str] = Field(default=None, description="Detail message when not available")
    data_sufficiency: Optional[str] = Field(default=None, description="Sufficiency status: VALID, INSUFFICIENT_DATA, or INVALID_INPUT")
    is_complete_national_aqi: Optional[bool] = Field(default=None, description="Completeness against full National AQI standard")
    calculation_method: Optional[str] = Field(default=None, description="Calculation methodology identifier")
    averaging_window_hours: Optional[float] = Field(default=None, description="Averaging window duration in hours")
    data_coverage_hours: Optional[float] = Field(default=None, description="Count of valid hourly buckets represented in the 24-hour window")
    is_provisional: Optional[bool] = Field(default=None, description="True if estimate is provisional")
