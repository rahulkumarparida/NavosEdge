"""
Manager Server Configuration
"""

import os
from pathlib import Path

# Load .env configuration if present
try:
    from dotenv import load_dotenv
    _project_root = Path(__file__).resolve().parent.parent.parent
    _env_path = _project_root / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
    else:
        load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from app.constants import (
    HOST_DEFAULT,
    PORT_DEFAULT,
    ENV_HOST_KEY,
    ENV_PORT_KEY,
    INACTIVE_TIMEOUT_SECONDS_DEFAULT,
    ENV_INACTIVE_TIMEOUT_KEY,
    STATE_FILENAME,
    DEFAULT_LOCATIONS,
    UNO_Q_HOST_DEFAULT,
    UNO_Q_PORT_DEFAULT,
    UNO_Q_POLL_INTERVAL_SECONDS_DEFAULT,
    ENV_UNO_Q_URL_KEY,
    ENV_UNO_Q_IP_KEY,
    ENV_UNO_Q_PORT_KEY,
    ENV_UNO_Q_POLL_INTERVAL_KEY,
    ENV_UNO_Q_POLL_ENABLED_KEY,
)

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = DATA_DIR / STATE_FILENAME

HOST = os.getenv(ENV_HOST_KEY, HOST_DEFAULT)
PORT = int(os.getenv(ENV_PORT_KEY, str(PORT_DEFAULT)))

# ------------------------------------------------------------------
# UNO Q Integration & Polling Settings
# ------------------------------------------------------------------
_uno_q_url_env = os.getenv(ENV_UNO_Q_URL_KEY, os.getenv("UNO_Q_BASE_URL", "")).strip()
_uno_q_ip_env = os.getenv(ENV_UNO_Q_IP_KEY, os.getenv("UNO_Q_IP", "")).strip()
_uno_q_port_env = os.getenv(ENV_UNO_Q_PORT_KEY, os.getenv("UNO_Q_PORT", str(UNO_Q_PORT_DEFAULT))).strip()

if _uno_q_url_env:
    UNO_Q_BASE_URL = _uno_q_url_env.rstrip("/")
elif _uno_q_ip_env:
    UNO_Q_BASE_URL = f"http://{_uno_q_ip_env}:{_uno_q_port_env}"
else:
    UNO_Q_BASE_URL = f"http://{UNO_Q_HOST_DEFAULT}:{UNO_Q_PORT_DEFAULT}"

UNO_Q_POLL_INTERVAL_S = float(os.getenv(ENV_UNO_Q_POLL_INTERVAL_KEY, str(UNO_Q_POLL_INTERVAL_SECONDS_DEFAULT)))
UNO_Q_POLL_ENABLED = os.getenv(ENV_UNO_Q_POLL_ENABLED_KEY, "true").lower() in ("true", "1", "yes")

# Time in seconds after which a node is considered inactive if no new reading arrives
_custom_timeout = os.getenv(ENV_INACTIVE_TIMEOUT_KEY)
if _custom_timeout:
    INACTIVE_TIMEOUT_SECONDS = int(_custom_timeout)
else:
    # Scale inactive timeout relative to polling interval if polling is enabled
    INACTIVE_TIMEOUT_SECONDS = max(INACTIVE_TIMEOUT_SECONDS_DEFAULT, int(UNO_Q_POLL_INTERVAL_S * 2 + 10))

# Re-export DEFAULT_LOCATIONS for backward compatibility
DEFAULT_LOCATIONS = DEFAULT_LOCATIONS


def get_uno_q_base_url() -> str:
    """Returns the currently active UNO Q base URL (env var takes precedence)."""
    global UNO_Q_BASE_URL
    return os.getenv("NAVOS_UNO_Q_URL", UNO_Q_BASE_URL).rstrip("/")


def set_uno_q_config(
    ip: str,
    port: int = 8420,
    poll_enabled: Optional[bool] = None,
    persist_env: bool = True,
) -> str:
    """
    Dynamically updates runtime UNO Q IP configuration and optionally persists to .env.
    """
    global UNO_Q_BASE_URL, UNO_Q_POLL_ENABLED
    url = f"http://{ip}:{port}"
    UNO_Q_BASE_URL = url
    os.environ["NAVOS_UNO_Q_IP"] = ip
    os.environ["NAVOS_UNO_Q_PORT"] = str(port)
    os.environ["NAVOS_UNO_Q_URL"] = url
    os.environ["UNO_Q_HOST_DEFAULT"] = ip

    if poll_enabled is not None:
        UNO_Q_POLL_ENABLED = bool(poll_enabled)
        os.environ["NAVOS_POLL_ENABLED"] = "true" if poll_enabled else "false"

    if persist_env:
        try:
            import sys
            _root = Path(__file__).resolve().parent.parent.parent
            if str(_root) not in sys.path:
                sys.path.insert(0, str(_root))
            from scripts.update_env_ip import update_env_file
            update_env_file(ip=ip, port=port, poll_enabled=poll_enabled)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Failed to persist updated IP to .env: %s", e)

    return url


