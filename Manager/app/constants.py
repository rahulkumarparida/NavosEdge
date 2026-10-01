"""
constants.py — Centralized constants for Manager module.
Single source of truth for host, port, timeout values, node mappings, and system info.
"""

from typing import Dict

# ------------------------------------------------------------------
# Server Network & Host Defaults
# ------------------------------------------------------------------
HOST_DEFAULT: str = "0.0.0.0"
PORT_DEFAULT: int = 8430
ENV_HOST_KEY: str = "NAVOS_MANAGER_HOST"
ENV_PORT_KEY: str = "NAVOS_MANAGER_PORT"

# ------------------------------------------------------------------
# Inactive Node Timeout & Monitoring
# ------------------------------------------------------------------
# Time in seconds after which a node is considered inactive if no new reading arrives
INACTIVE_TIMEOUT_SECONDS_DEFAULT: int = 15
ENV_INACTIVE_TIMEOUT_KEY: str = "NAVOS_INACTIVE_TIMEOUT_S"

# ------------------------------------------------------------------
# State Storage & File Paths
# ------------------------------------------------------------------
STATE_FILENAME: str = "manager_state.json"

# ------------------------------------------------------------------
# Default Location Mappings for Known Nodes
# ------------------------------------------------------------------
DEFAULT_LOCATIONS: Dict[str, str] = {
    "navos-01": "Bhubaneswar",
    "navos-02": "Cuttack",
    "NAVOS-SIM-001": "Bhubaneswar Station A",
    "NAVOS-SIM-002": "Cuttack Station B",
    "uno-q-001": "UNO Q Edge Node 1",
}

# ------------------------------------------------------------------
# API Metadata & Event Streaming
# ------------------------------------------------------------------
SYSTEM_VERSION: str = "1.0.0"
SSE_HEARTBEAT_TIMEOUT_S: float = 10.0
