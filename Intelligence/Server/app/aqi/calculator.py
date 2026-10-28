"""
AQI Calculator implementation adhering to regulatory EPA / CPCB breakpoint standards.
"""

from datetime import datetime, timezone
import math
from typing import Dict, List, Optional, Tuple

from app.aqi.schemas import AQICalculationResult
from app.core.constants import BREAKPOINTS_EPA, BREAKPOINTS_CPCB, DEFAULT_AQI_STANDARD


class AQICalculator:
    """Calculates AQI sub-indices and overall AQI using standard regulatory breakpoint tables."""

    def __init__(self, standard: Optional[str] = None) -> None:
        selected = (standard or DEFAULT_AQI_STANDARD).upper()
        if selected == "CPCB":
            self.standard = "CPCB"
            self.breakpoints = BREAKPOINTS_CPCB
        else:
            self.standard = "EPA"
            self.breakpoints = BREAKPOINTS_EPA

    def calculate_sub_index(self, pollutant: str, conc: float) -> float:
        """Calculate AQI sub-index for a given pollutant and concentration."""
        if not math.isfinite(conc) or conc < 0:
            return 0.0

        table = self.breakpoints.get(pollutant)
        if not table:
            return 0.0

        for i, (c_low, c_high, i_low, i_high) in enumerate(table):
            # Check for inter-bracket gap (e.g. between 250.0 and 251.0 or 30.0 and 30.1)
            if i > 0:
                prev_c_high = table[i - 1][1]
                prev_i_high = table[i - 1][3]
                if prev_c_high < conc < c_low:
                    slope = (i_low - prev_i_high) / (c_low - prev_c_high)
                    return round(slope * (conc - prev_c_high) + prev_i_high, 2)

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
        data_sufficiency: str = "VALID",
        averaging_window_hours: float = 24.0,
        data_coverage_hours: float = 0.0,
        is_provisional: bool = False,
    ) -> AQICalculationResult:
        """Calculate overall AQI, dominant pollutant, sub-indices and category."""
        # Handle invalid / non-finite inputs explicitly
        is_invalid = (
            not (math.isfinite(pm1_0) and math.isfinite(pm2_5) and math.isfinite(pm10))
            or pm2_5 < 0
            or pm10 < 0
            or pm1_0 < 0
        )
        if is_invalid or data_sufficiency == "INVALID_INPUT":
            if timestamp is None:
                timestamp = datetime.now(timezone.utc)
            safe_pm1 = pm1_0 if math.isfinite(pm1_0) else 0.0
            safe_pm25 = pm2_5 if math.isfinite(pm2_5) else 0.0
            safe_pm10 = pm10 if math.isfinite(pm10) else 0.0
            return AQICalculationResult(
                status="invalid_input",
                aqi=0.0,
                category="Invalid Input",
                dominant_pollutant="NONE",
                pm={"PM1_0": safe_pm1, "PM2_5": safe_pm25, "PM10": safe_pm10},
                sub_indices={},
                timestamp=timestamp,
                node_id=node_id,
                data_sufficiency="INVALID_INPUT",
                is_complete_national_aqi=False,
                calculation_method=f"{self.standard}_PM_ESTIMATE",
                averaging_window_hours=averaging_window_hours,
                data_coverage_hours=data_coverage_hours,
                is_provisional=is_provisional,
            )

        if self.standard == "CPCB":
            # Under CPCB NAQI: PM1.0 is not a regulatory pollutant.
            # Only PM2.5 and PM10 sub-indices are calculated and eligible for dominant pollutant.
            sub_indices = {
                "PM2_5": self.calculate_sub_index("PM2_5", pm2_5),
                "PM10": self.calculate_sub_index("PM10", pm10),
            }
        else:
            # EPA Mode: include PM1.0 sub-index if breakpoint configured, plus PM2.5 and PM10
            sub_indices = {}
            if "PM1_0" in self.breakpoints:
                sub_indices["PM1_0"] = self.calculate_sub_index("PM1_0", pm1_0)
            sub_indices["PM2_5"] = self.calculate_sub_index("PM2_5", pm2_5)
            sub_indices["PM10"] = self.calculate_sub_index("PM10", pm10)

        dominant_pollutant = max(sub_indices, key=lambda k: sub_indices[k])
        overall_aqi = sub_indices[dominant_pollutant]
        category = self.get_category(overall_aqi)

        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        # Hardware measures PM and uncalibrated gas sensor voltages;
        # full National AQI requires certified gaseous criteria pollutants (SO2, NO2, CO, O3).
        is_complete = False

        status = "available"

        return AQICalculationResult(
            status=status,
            aqi=overall_aqi,
            category=category,
            dominant_pollutant=dominant_pollutant,
            pm={"PM1_0": pm1_0, "PM2_5": pm2_5, "PM10": pm10},
            sub_indices=sub_indices,
            timestamp=timestamp,
            node_id=node_id,
            data_sufficiency=data_sufficiency,
            is_complete_national_aqi=is_complete,
            calculation_method=f"{self.standard}_PM_ESTIMATE",
            averaging_window_hours=averaging_window_hours,
            data_coverage_hours=data_coverage_hours,
            is_provisional=is_provisional,
        )
