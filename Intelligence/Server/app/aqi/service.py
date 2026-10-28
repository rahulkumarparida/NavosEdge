from datetime import datetime, timezone, timedelta
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.aqi.calculator import AQICalculator
from app.aqi.schemas import AQICalculationResult, LatestAQIResponse
from app.aqi.store import AQIStore
from app.core.constants import DEFAULT_AQI_STANDARD
from app.schemas.sensor import SensorPayload

logger = logging.getLogger(__name__)

# Minimum hours of valid data required in a 24-hour window for CPCB regulatory sufficiency
CPCB_REQUIRED_HOURS: float = 16.0
AVERAGING_WINDOW_HOURS: float = 24.0


class AQIService:
    """High-level AQI service managing rolling moving-average windows, data sufficiency, and persistence."""

    def __init__(self, storage_path: Path, standard: Optional[str] = None) -> None:
        self.standard = (standard or DEFAULT_AQI_STANDARD).upper()
        self.calculator = AQICalculator(standard=self.standard)
        self.store = AQIStore(storage_path=storage_path)
        # In-memory rolling history buffer per node: node_id -> list of (timestamp, pm1_0, pm2_5, pm10)
        self._history: Dict[str, List[Tuple[datetime, float, float, float]]] = {}
        # Load any existing persisted AQI on init
        self.store.load_latest()

    def _normalize_dt(self, dt: Any) -> datetime:
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def process_reading(self, payload: SensorPayload) -> AQICalculationResult:
        """Calculate moving-average AQI for a new reading, check data sufficiency, and persist latest."""
        pm_obj = payload.particulate_matter
        if isinstance(pm_obj, dict):
            pm1_0 = float(pm_obj.get("PM1_0", 0.0))
            pm2_5 = float(pm_obj.get("PM2_5", 0.0))
            pm10 = float(pm_obj.get("PM10", 0.0))
        else:
            pm1_0 = float(pm_obj.PM1_0)
            pm2_5 = float(pm_obj.PM2_5)
            pm10 = float(pm_obj.PM10)

        node_id = payload.node_id or "default"
        reading_dt = self._normalize_dt(payload.timestamp)

        # Validate sensor inputs (finite and non-negative)
        is_invalid = (
            not (math.isfinite(pm1_0) and math.isfinite(pm2_5) and math.isfinite(pm10))
            or pm2_5 < 0
            or pm10 < 0
            or pm1_0 < 0
        )
        if is_invalid:
            result = self.calculator.calculate(
                pm1_0=pm1_0 if math.isfinite(pm1_0) else 0.0,
                pm2_5=pm2_5 if math.isfinite(pm2_5) else 0.0,
                pm10=pm10 if math.isfinite(pm10) else 0.0,
                timestamp=reading_dt,
                node_id=node_id,
                data_sufficiency="INVALID_INPUT",
            )
            self.store.save_latest(result)
            return result

        # Maintain rolling 24-hour window
        node_hist = self._history.setdefault(node_id, [])
        node_hist.append((reading_dt, pm1_0, pm2_5, pm10))
        # Ensure chronological ordering to guard against out-of-order replay
        node_hist.sort(key=lambda pt: pt[0])
        # Prune older than 24 hours relative to latest reading
        latest_dt = node_hist[-1][0]
        cutoff = latest_dt - timedelta(hours=AVERAGING_WINDOW_HOURS)
        node_hist = [entry for entry in node_hist if entry[0] >= cutoff]
        self._history[node_id] = node_hist

        # Count distinct valid hourly buckets represented in the 24h rolling window.
        # Each entry[0] is a normalized UTC datetime. Multiple readings within the same
        # calendar hour map to the same bucket key and count as exactly one covered hour.
        hourly_buckets = {
            (entry[0].year, entry[0].month, entry[0].day, entry[0].hour)
            for entry in node_hist
        }
        coverage_hours = float(len(hourly_buckets))

        # CPCB data sufficiency: at least 16 distinct hourly buckets in the 24h window
        if coverage_hours >= CPCB_REQUIRED_HOURS:
            data_sufficiency = "VALID"
            is_provisional = False
        else:
            data_sufficiency = "INSUFFICIENT_DATA"
            is_provisional = True

        # Moving average across rolling window (prevents single instantaneous spike from masquerading as 24h AQI)
        avg_pm1_0 = sum(pt[1] for pt in node_hist) / len(node_hist)
        avg_pm2_5 = sum(pt[2] for pt in node_hist) / len(node_hist)
        avg_pm10 = sum(pt[3] for pt in node_hist) / len(node_hist)

        result = self.calculator.calculate(
            pm1_0=round(avg_pm1_0, 2),
            pm2_5=round(avg_pm2_5, 2),
            pm10=round(avg_pm10, 2),
            timestamp=reading_dt,
            node_id=payload.node_id,
            data_sufficiency=data_sufficiency,
            averaging_window_hours=AVERAGING_WINDOW_HOURS,
            data_coverage_hours=round(coverage_hours, 2),
            is_provisional=is_provisional,
        )
        self.store.save_latest(result)
        logger.debug(
            "AQI calculated for node %s (%s, coverage=%.2fh): AQI=%.2f [%s]",
            payload.node_id,
            self.standard,
            coverage_hours,
            result.aqi,
            data_sufficiency,
        )
        return result

    def get_latest(self, node_id: Optional[str] = None) -> LatestAQIResponse:
        """Retrieve latest calculated AQI or return clear not_available response."""
        latest = self.store.get_latest(node_id=node_id)
        if latest is None:
            return LatestAQIResponse(
                status="not_available",
                detail="No AQI calculation available yet",
            )
        return LatestAQIResponse(
            status=latest.status,
            aqi=latest.aqi,
            category=latest.category,
            dominant_pollutant=latest.dominant_pollutant,
            pm=latest.pm,
            sub_indices=latest.sub_indices,
            timestamp=latest.timestamp,
            node_id=latest.node_id,
            data_sufficiency=latest.data_sufficiency,
            is_complete_national_aqi=latest.is_complete_national_aqi,
            calculation_method=latest.calculation_method,
            averaging_window_hours=latest.averaging_window_hours,
            data_coverage_hours=latest.data_coverage_hours,
            is_provisional=latest.is_provisional,
        )
