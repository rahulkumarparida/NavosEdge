"""Schemas for AQI calculation results and API responses."""

from datetime import datetime
from typing import Dict, Optional
from pydantic import BaseModel, Field


class AQICalculationResult(BaseModel):
    """Result of an AQI calculation for a specific reading."""

    status: str = "available"
    aqi: float = Field(..., ge=0.0, description="Air Quality Index value (PM-based estimate or compliant)")
    category: str = Field(..., description="Indian AQI category (e.g. Good, Satisfactory, Moderate, Poor, Very Poor, Severe)")
    dominant_pollutant: str = Field(..., description="Pollutant responsible for maximum AQI sub-index")
    pm: Dict[str, float] = Field(..., description="Relevant PM values (PM1_0, PM2_5, PM10)")
    sub_indices: Dict[str, float] = Field(..., description="Individual sub-index for each eligible parameter")
    timestamp: datetime = Field(..., description="Timestamp of the sensor reading")
    node_id: Optional[str] = Field(default=None, description="Identifier of the reporting node")
    calculation_basis: str = Field(default="PM_BASED_ESTIMATE", description="Calculation basis: PM_BASED_ESTIMATE or CPCB_COMPLIANT")
    cpcb_compliant: bool = Field(default=False, description="True only if at least 3 eligible regulatory pollutants are monitored")
    data_sufficiency: str = Field(default="INSUFFICIENT_POLLUTANTS", description="Data sufficiency status per CPCB guideline")
    official_cpcb_aqi: Optional[float] = Field(default=None, description="Official CPCB AQI (None if <3 eligible pollutants)")
    pm_based_aqi: Optional[float] = Field(default=None, description="PM-based AQI estimate")


class LatestAQIResponse(BaseModel):
    """API response contract for GET /aqi/latest."""

    status: str = Field(..., description="'available', 'pm_based_estimate', or 'not_available'")
    aqi: Optional[float] = Field(default=None, description="Most recently calculated AQI value")
    category: Optional[str] = Field(default=None, description="AQI qualitative category")
    dominant_pollutant: Optional[str] = Field(default=None, description="Dominant pollutant key")
    pm: Optional[Dict[str, float]] = Field(default=None, description="PM values corresponding to latest AQI")
    sub_indices: Optional[Dict[str, float]] = Field(default=None, description="PM and gas sub-indices")
    timestamp: Optional[datetime] = Field(default=None, description="Timestamp of latest calculation")
    node_id: Optional[str] = Field(default=None, description="Node ID of latest calculation")
    calculation_basis: Optional[str] = Field(default="PM_BASED_ESTIMATE", description="Calculation basis")
    cpcb_compliant: bool = Field(default=False, description="Whether calculation meets official CPCB 3+ pollutant rule")
    data_sufficiency: Optional[str] = Field(default="INSUFFICIENT_POLLUTANTS", description="Data sufficiency status")
    official_cpcb_aqi: Optional[float] = Field(default=None, description="Official CPCB AQI value (null if insufficient pollutants)")
    pm_based_aqi: Optional[float] = Field(default=None, description="PM-based AQI estimate value")
    detail: Optional[str] = Field(default=None, description="Detail message when not available or limitations")
