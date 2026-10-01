"""
AQI Calculator implementation adhering to regulatory EPA / CPCB breakpoint standards.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.aqi.schemas import AQICalculationResult
from app.core.constants import BREAKPOINTS_EPA, BREAKPOINTS_CPCB


class AQICalculator:
    """Calculates AQI sub-indices and overall AQI using standard regulatory breakpoint tables."""

    def __init__(self, standard: str = "EPA") -> None:
        self.standard = standard.upper()
        if self.standard == "CPCB":
            self.breakpoints = BREAKPOINTS_CPCB
        else:
            self.standard = "EPA"
            self.breakpoints = BREAKPOINTS_EPA

    def calculate_sub_index(self, pollutant: str, conc: float) -> float:
        """Calculate AQI sub-index for a given pollutant and concentration."""
        if conc < 0:
            return 0.0

        table = self.breakpoints.get(pollutant, self.breakpoints["PM2_5"])
        for c_low, c_high, i_low, i_high in table:
            if c_low <= conc <= c_high:
                slope = (i_high - i_low) / (c_high - c_low)
                return round(slope * (conc - c_low) + i_low, 2)

        # If concentration exceeds highest breakpoint, extrapolate using top bracket slope
        c_low, c_high, i_low, i_high = table[-1]
        slope = (i_high - i_low) / (c_high - c_low)
        extrapolated = slope * (conc - c_low) + i_low
        return round(extrapolated, 2)

    def get_category(self, aqi: float) -> str:
        """Map AQI value to category string according to active standard."""
        if self.standard == "CPCB":
            if aqi <= 50:
                return "Good"
            elif aqi <= 100:
                return "Satisfactory"
            elif aqi <= 200:
                return "Moderate"
            elif aqi <= 300:
                return "Poor"
            elif aqi <= 400:
                return "Very Poor"
            else:
                return "Severe"
        else:
            # EPA Standard
            if aqi <= 50:
                return "Good"
            elif aqi <= 100:
                return "Moderate"
            elif aqi <= 150:
                return "Unhealthy for Sensitive Groups"
            elif aqi <= 200:
                return "Unhealthy"
            elif aqi <= 300:
                return "Very Unhealthy"
            else:
                return "Hazardous"

    def calculate(
        self,
        pm1_0: float,
        pm2_5: float,
        pm10: float,
        timestamp: Optional[datetime] = None,
        node_id: Optional[str] = None,
    ) -> AQICalculationResult:
        """Calculate overall AQI, dominant pollutant, sub-indices and category."""
        sub_indices = {
            "PM1_0": self.calculate_sub_index("PM1_0", pm1_0),
            "PM2_5": self.calculate_sub_index("PM2_5", pm2_5),
            "PM10": self.calculate_sub_index("PM10", pm10),
        }

        dominant_pollutant = max(sub_indices, key=lambda k: sub_indices[k])
        overall_aqi = sub_indices[dominant_pollutant]
        category = self.get_category(overall_aqi)

        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        return AQICalculationResult(
            status="available",
            aqi=overall_aqi,
            category=category,
            dominant_pollutant=dominant_pollutant,
            pm={"PM1_0": pm1_0, "PM2_5": pm2_5, "PM10": pm10},
            sub_indices=sub_indices,
            timestamp=timestamp,
            node_id=node_id,
        )
