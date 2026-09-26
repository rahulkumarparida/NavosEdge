"""Persistent storage for the latest AQI result using a lightweight JSON file."""

import json
import logging
import os
from pathlib import Path
from typing import Dict, Optional

from app.aqi.schemas import AQICalculationResult

logger = logging.getLogger(__name__)


class AQIStore:
    """Manages lightweight persistent storage of calculated AQI results."""

    def __init__(self, storage_path: Path) -> None:
        self.storage_path = Path(storage_path)
        self._latest: Optional[AQICalculationResult] = None
        self._latest_by_node: Dict[str, AQICalculationResult] = {}
        # Ensure parent directory exists
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def load_latest(self) -> Optional[AQICalculationResult]:
        """Load latest AQI result from persistent JSON file if available."""
        if not self.storage_path.exists():
            return None
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            result = AQICalculationResult.model_validate(data)
            self._latest = result
            if result.node_id:
                self._latest_by_node[result.node_id] = result
            return result
        except Exception as e:
            logger.warning("Failed to load latest AQI file from %s: %s", self.storage_path, e)
            return None

    def save_latest(self, result: AQICalculationResult) -> None:
        """Overwrite and persist the latest AQI result atomically."""
        self._latest = result
        if result.node_id:
            self._latest_by_node[result.node_id] = result

        try:
            data = result.model_dump(mode="json")
            temp_path = self.storage_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(temp_path, self.storage_path)
        except Exception as e:
            logger.error("Failed to write AQI result to %s: %s", self.storage_path, e)

    def get_latest(self, node_id: Optional[str] = None) -> Optional[AQICalculationResult]:
        """Retrieve the latest AQI result from memory or file."""
        if node_id and node_id in self._latest_by_node:
            return self._latest_by_node[node_id]

        if self._latest is not None:
            return self._latest

        # Try loading from disk if memory cache is empty
        return self.load_latest()
