"""
AQI Calculator implementation adhering to Indian CPCB National Air Quality Index
methodology and EPA breakpoint standards.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from app.aqi.schemas import AQICalculationResult
from app.core.constants import BREAKPOINTS_CPCB, BREAKPOINTS_EPA, DEFAULT_AQI_STANDARD


class AQICalculator:
    """Calculates AQI sub-indices and overall AQI using regulatory breakpoint tables."""

    def __init__(self, standard: str = "CPCB") -> None:
        self.standard = standard.upper()
        if self.standard == "EPA":
            self.breakpoints = BREAKPOINTS_EPA
        else:
            self.standard = "CPCB"
            self.breakpoints = BREAKPOINTS_CPCB

    def calculate_sub_index(self, pollutant: str, conc: float) -> Optional[float]:
        """
        Calculate AQI sub-index for a given pollutant and concentration.
        Interpolation formula:
            Sub-index = ((I_high - I_low) / (BP_high - BP_low)) * (conc - BP_low) + I_low
        """
        if conc is None or conc < 0:
            return None

        # PM1.0 is NOT a regulatory pollutant in Indian CPCB standards
        if pollutant == "PM1_0":
            if self.standard == "CPCB":
                return None
            table = self.breakpoints.get("PM1_0")
            if not table:
                return None
        else:
            table = self.breakpoints.get(pollutant)

        if not table:
            return None

        for c_low, c_high, i_low, i_high in table:
            if c_low <= conc <= c_high:
                slope = (i_high - i_low) / (c_high - c_low)
                return round(slope * (conc - c_low) + i_low, 2)

        # Above highest breakpoint: extrapolate using top bracket slope
        c_low, c_high, i_low, i_high = table[-1]
        slope = (i_high - i_low) / (c_high - c_low)
        extrapolated = slope * (conc - c_low) + i_low
        return round(extrapolated, 2)

    def get_category(self, aqi: float) -> str:
        """Map AQI value to category string according to active standard."""
        if aqi is None:
            return "Unavailable"

        if self.standard == "CPCB":
            # Canonical Indian National AQI Categories
            if aqi <= 50.0:
                return "Good"
            elif aqi <= 100.0:
                return "Satisfactory"
            elif aqi <= 200.0:
                return "Moderate"
            elif aqi <= 300.0:
                return "Poor"
            elif aqi <= 400.0:
                return "Very Poor"
            else:
                return "Severe"
        else:
            # EPA Standard
            if aqi <= 50.0:
                return "Good"
            elif aqi <= 100.0:
                return "Moderate"
            elif aqi <= 150.0:
                return "Unhealthy for Sensitive Groups"
            elif aqi <= 200.0:
                return "Unhealthy"
            elif aqi <= 300.0:
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
        other_pollutants: Optional[Dict[str, float]] = None,
    ) -> AQICalculationResult:
        """
        Calculate overall AQI, dominant pollutant, sub-indices and category.

        Under CPCB methodology:
        - At least 3 eligible regulatory pollutants (including PM2.5 or PM10)
          are required for an official CPCB AQI.
        - PM1.0 is excluded from CPCB sub-index calculation.
        - Raw MQ sensor voltages cannot substitute for regulatory gas measurements.
        - When only PM parameters are available, the result is marked as PM_BASED_ESTIMATE.
        """
        sub_indices: Dict[str, float] = {}

        # 1. PM sub-indices
        sub_pm25 = self.calculate_sub_index("PM2_5", pm2_5) if pm2_5 is not None and pm2_5 >= 0 else None
        if sub_pm25 is not None:
            sub_indices["PM2_5"] = sub_pm25

        sub_pm10 = self.calculate_sub_index("PM10", pm10) if pm10 is not None and pm10 >= 0 else None
        if sub_pm10 is not None:
            sub_indices["PM10"] = sub_pm10

        if self.standard == "EPA":
            sub_pm1 = self.calculate_sub_index("PM1_0", pm1_0) if pm1_0 is not None and pm1_0 >= 0 else None
            if sub_pm1 is not None:
                sub_indices["PM1_0"] = sub_pm1

        # 2. Other calibrated pollutants if present
        if other_pollutants:
            for p_name, p_val in other_pollutants.items():
                if p_val is not None and p_val >= 0:
                    s_idx = self.calculate_sub_index(p_name, p_val)
                    if s_idx is not None:
                        sub_indices[p_name] = s_idx

        # 3. CPCB compliance assessment
        eligible_pollutants = set(sub_indices.keys())
        has_pm = "PM2_5" in eligible_pollutants or "PM10" in eligible_pollutants
        pollutant_count = len(eligible_pollutants)

        if self.standard == "CPCB":
            cpcb_compliant = bool(pollutant_count >= 3 and has_pm)
            if cpcb_compliant:
                calculation_basis = "CPCB_COMPLIANT"
                data_sufficiency = "SUFFICIENT"
                status = "available"
            elif has_pm:
                calculation_basis = "PM_BASED_ESTIMATE"
                data_sufficiency = "INSUFFICIENT_POLLUTANTS"
                status = "available"
            else:
                calculation_basis = "INSUFFICIENT_DATA"
                data_sufficiency = "INSUFFICIENT_POLLUTANTS"
                status = "not_available"
        else:
            cpcb_compliant = False
            calculation_basis = "EPA_STANDARD"
            data_sufficiency = "SUFFICIENT" if has_pm else "INSUFFICIENT_DATA"
            status = "available" if has_pm else "not_available"

        if sub_indices:
            dominant_pollutant = max(sub_indices, key=lambda k: sub_indices[k])
            overall_aqi = sub_indices[dominant_pollutant]
            category = self.get_category(overall_aqi)
        else:
            dominant_pollutant = "None"
            overall_aqi = 0.0
            category = "Unavailable"
            status = "not_available"

        official_cpcb_aqi = overall_aqi if cpcb_compliant else None
        pm_based_aqi = overall_aqi if has_pm else None

        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        return AQICalculationResult(
            status=status,
            aqi=overall_aqi,
            category=category,
            dominant_pollutant=dominant_pollutant,
            pm={
                "PM1_0": pm1_0 if pm1_0 is not None else 0.0,
                "PM2_5": pm2_5 if pm2_5 is not None else 0.0,
                "PM10": pm10 if pm10 is not None else 0.0,
            },
            sub_indices=sub_indices,
            timestamp=timestamp,
            node_id=node_id,
            calculation_basis=calculation_basis,
            cpcb_compliant=cpcb_compliant,
            data_sufficiency=data_sufficiency,
            official_cpcb_aqi=official_cpcb_aqi,
            pm_based_aqi=pm_based_aqi,
        )
