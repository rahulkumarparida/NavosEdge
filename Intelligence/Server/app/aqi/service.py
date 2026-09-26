"""Service orchestrating AQI calculation, persistence and query operations."""

import logging
from pathlib import Path
from typing import Optional

from app.aqi.calculator import AQICalculator
from app.aqi.schemas import AQICalculationResult, LatestAQIResponse
from app.aqi.store import AQIStore
from app.schemas.sensor import SensorPayload

logger = logging.getLogger(__name__)


class AQIService:
    """High-level AQI service managing calculation workflow and persistence."""

    def __init__(self, storage_path: Path, standard: str = "EPA") -> None:
        self.calculator = AQICalculator(standard=standard)
        self.store = AQIStore(storage_path=storage_path)
        # Load any existing persisted AQI on init
        self.store.load_latest()

    def process_reading(self, payload: SensorPayload) -> AQICalculationResult:
        """Calculate AQI for a new valid reading and persist the latest result."""
        pm = payload.particulate_matter
        result = self.calculator.calculate(
            pm1_0=pm.PM1_0,
            pm2_5=pm.PM2_5,
            pm10=pm.PM10,
            timestamp=payload.timestamp,
            node_id=payload.node_id,
        )
        self.store.save_latest(result)
        logger.debug("AQI calculated for node %s: AQI=%.2f", payload.node_id, result.aqi)
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
            status="available",
            aqi=latest.aqi,
            category=latest.category,
            dominant_pollutant=latest.dominant_pollutant,
            pm=latest.pm,
            sub_indices=latest.sub_indices,
            timestamp=latest.timestamp,
            node_id=latest.node_id,
        )
