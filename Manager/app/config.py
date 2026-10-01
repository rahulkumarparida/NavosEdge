"""
Manager Server Configuration
"""

import os
from pathlib import Path
from app.constants import (
    HOST_DEFAULT,
    PORT_DEFAULT,
    ENV_HOST_KEY,
    ENV_PORT_KEY,
    INACTIVE_TIMEOUT_SECONDS_DEFAULT,
    ENV_INACTIVE_TIMEOUT_KEY,
    STATE_FILENAME,
    DEFAULT_LOCATIONS,
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = DATA_DIR / STATE_FILENAME

HOST = os.getenv(ENV_HOST_KEY, HOST_DEFAULT)
PORT = int(os.getenv(ENV_PORT_KEY, str(PORT_DEFAULT)))

# Time in seconds after which a node is considered inactive if no new reading arrives
INACTIVE_TIMEOUT_SECONDS = int(os.getenv(ENV_INACTIVE_TIMEOUT_KEY, str(INACTIVE_TIMEOUT_SECONDS_DEFAULT)))

# Re-export DEFAULT_LOCATIONS for backward compatibility
DEFAULT_LOCATIONS = DEFAULT_LOCATIONS
