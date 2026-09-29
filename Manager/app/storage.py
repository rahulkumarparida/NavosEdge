"""
Local File-based State Storage for NavosEdge Manager
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any

from app.config import STATE_FILE

logger = logging.getLogger(__name__)


class ManagerStorage:
    def __init__(self, file_path: Path = STATE_FILE):
        self.file_path = file_path

    def load_state(self) -> Dict[str, Any]:
        """Loads nodes state dictionary from JSON file."""
        if not self.file_path.exists():
            logger.info("Storage file %s does not exist. Starting fresh.", self.file_path)
            return {}

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                logger.info("Successfully loaded state for %d nodes from storage.", len(data.get("nodes", {})))
                return data.get("nodes", {})
        except Exception as e:
            logger.error("Failed to load manager state from %s: %s", self.file_path, e)
            return {}

    def save_state(self, nodes_dict: Dict[str, Any]) -> bool:
        """Saves nodes state dictionary to JSON file cleanly."""
        try:
            temp_file = self.file_path.with_suffix(".tmp")
            data = {"nodes": nodes_dict}
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            temp_file.replace(self.file_path)
            return True
        except Exception as e:
            logger.error("Failed to save manager state to %s: %s", self.file_path, e)
            return False
