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
INACTIVE_TIMEOUT_SECONDS_DEFAULT: int = 60
ENV_INACTIVE_TIMEOUT_KEY: str = "NAVOS_INACTIVE_TIMEOUT_S"

# ------------------------------------------------------------------
# UNO Q Edge Node Integration & Polling Defaults
# ------------------------------------------------------------------
UNO_Q_HOST_DEFAULT: str = "127.0.0.1"
UNO_Q_PORT_DEFAULT: int = 8420
UNO_Q_POLL_INTERVAL_SECONDS_DEFAULT: float = 3600.0  # Default 1 hour polling interval

ENV_UNO_Q_URL_KEY: str = "NAVOS_UNO_Q_URL"
ENV_UNO_Q_IP_KEY: str = "NAVOS_UNO_Q_IP"
ENV_UNO_Q_PORT_KEY: str = "NAVOS_UNO_Q_PORT"
ENV_UNO_Q_POLL_INTERVAL_KEY: str = "NAVOS_POLL_INTERVAL_S"
ENV_UNO_Q_POLL_ENABLED_KEY: str = "NAVOS_POLL_ENABLED"


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
