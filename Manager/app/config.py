"""
Manager Server Configuration
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = DATA_DIR / "manager_state.json"

HOST = os.getenv("NAVOS_MANAGER_HOST", "0.0.0.0")
PORT = int(os.getenv("NAVOS_MANAGER_PORT", "8430"))

# Time in seconds after which a node is considered inactive if no new reading arrives
INACTIVE_TIMEOUT_SECONDS = int(os.getenv("NAVOS_INACTIVE_TIMEOUT_S", "15"))

# Default location mappings for known test nodes
DEFAULT_LOCATIONS = {
    "navos-01": "Bhubaneswar",
    "navos-02": "Cuttack",
    "NAVOS-SIM-001": "Bhubaneswar Station A",
    "NAVOS-SIM-002": "Cuttack Station B",
    "uno-q-001": "UNO Q Edge Node 1",
}
