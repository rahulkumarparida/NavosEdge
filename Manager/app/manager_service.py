"""
Core Manager Service — Node Tracking, Aggregation & SSE Event Distribution
"""

import asyncio
from datetime import datetime, timezone
import logging
import math
import os
from typing import Any, Dict, List, Optional, Set, Union

from app.config import DEFAULT_LOCATIONS, INACTIVE_TIMEOUT_SECONDS
from app.models import NodeState, NodeTelemetryPayload, OverallData, OverviewResponse
from app.storage import ManagerStorage

logger = logging.getLogger(__name__)


def safe_float(val: Any, default: Optional[float] = 0.0) -> Optional[float]:
    """
    Safely converts a value to float, handling None, null, empty string,
    and invalid types without throwing exceptions.
    Preserves valid zero (0, 0.0) and negative values.
    """
    if val is None:
        return default
    try:
        if isinstance(val, str):
            v_strip = val.strip().lower()
            if v_strip in ("", "null", "none", "nan"):
                return default
        f = float(val)
        if math.isnan(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


BREAKPOINTS_EPA_PM25 = [
    (0.0, 12.0, 0.0, 50.0),
    (12.1, 35.4, 51.0, 100.0),
    (35.5, 55.4, 101.0, 150.0),
    (55.5, 150.4, 151.0, 200.0),
    (150.5, 250.4, 201.0, 300.0),
    (250.5, 350.4, 301.0, 400.0),
    (350.5, 500.4, 401.0, 500.0),
]
BREAKPOINTS_EPA_PM10 = [
    (0.0, 54.0, 0.0, 50.0),
    (55.0, 154.0, 51.0, 100.0),
    (155.0, 254.0, 101.0, 150.0),
    (255.0, 354.0, 151.0, 200.0),
    (355.0, 424.0, 201.0, 300.0),
    (425.0, 504.0, 301.0, 400.0),
    (505.0, 604.0, 401.0, 500.0),
]


def calculate_epa_aqi(pm2_5: float, pm10: float) -> Optional[float]:
    """Calculates overall regulatory EPA AQI based on PM2.5 and PM10 sub-indices."""
    def _sub_index(conc: float, table) -> float:
        if conc <= 0.0:
            return 0.0
        for c_low, c_high, i_low, i_high in table:
            if c_low <= conc <= c_high:
                slope = (i_high - i_low) / (c_high - c_low)
                return round(slope * (conc - c_low) + i_low, 2)
        c_low, c_high, i_low, i_high = table[-1]
        slope = (i_high - i_low) / (c_high - c_low)
        return round(slope * (conc - c_low) + i_low, 2)

    si_pm25 = _sub_index(pm2_5, BREAKPOINTS_EPA_PM25)
    si_pm10 = _sub_index(pm10, BREAKPOINTS_EPA_PM10)
    return max(si_pm25, si_pm10)


def normalize_telemetry(
    payload: Union[NodeTelemetryPayload, Dict[str, Any], Any],
    node_id: Optional[str] = None,
    default_location: Optional[str] = None,
    ip: Optional[str] = None,
    port: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Unified normalization for telemetry from both Push (HTTP POST)
    and Pull (UNO Q /latest polling) paths.

    Guarantees consistent Manager node state:
    - Missing or null temperature_C / humidity_pct safely normalize to 0.0.
    - Legitimate 0, 0.0, and valid negative values are preserved.
    - aqi is preserved if present (including 0.0), or calculated from PM if missing.
    - Missing or malformed pm fields safely default to 0.0.
    - Predictions and advisory default safely to empty dicts.
    """
    if isinstance(payload, NodeTelemetryPayload):
        raw: Dict[str, Any] = payload.model_dump()
    elif isinstance(payload, dict):
        raw = payload
    else:
        raise ValueError(f"Telemetry payload must be a dict or NodeTelemetryPayload, got {type(payload).__name__}")

    # Determine node_id
    target_node_id = node_id or raw.get("node_id")
    if not target_node_id:
        raise ValueError("Missing node_id in telemetry data")
    target_node_id = str(target_node_id).strip()
    if not target_node_id:
        raise ValueError("Empty node_id in telemetry data")

    # Determine location
    loc = raw.get("location")
    if not loc:
        loc = default_location or DEFAULT_LOCATIONS.get(target_node_id, f"Location-{target_node_id}")

    # Timestamp / last_seen
    ts = raw.get("timestamp")
    if not ts or not isinstance(ts, str):
        ts = datetime.now(timezone.utc).isoformat()
    else:
        try:
            parsed = datetime.fromisoformat(ts)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            ts = parsed.isoformat()
        except (ValueError, TypeError):
            ts = datetime.now(timezone.utc).isoformat()

    # Environmental: temperature_C and humidity_pct (supporting aliases)
    temp_c = safe_float(raw.get("temperature_C") if "temperature_C" in raw else raw.get("temperature"), default=0.0)
    hum_pct = safe_float(raw.get("humidity_pct") if "humidity_pct" in raw else raw.get("humidity"), default=0.0)

    # AQI: optional, support number, str, or dict objects {"aqi": ..., "value": ...}
    aqi_raw = raw.get("aqi")
    if isinstance(aqi_raw, dict):
        aqi_val = safe_float(aqi_raw.get("aqi") or aqi_raw.get("value") or aqi_raw.get("index"), default=None)
    else:
        aqi_val = safe_float(aqi_raw, default=None)

    if aqi_val is None:
        alt_aqi = raw.get("AQI") or raw.get("air_quality_index")
        if isinstance(alt_aqi, dict):
            aqi_val = safe_float(alt_aqi.get("aqi") or alt_aqi.get("value"), default=None)
        else:
            aqi_val = safe_float(alt_aqi, default=None)

    # PM readings: support 'pm', 'particulate_matter', or flat keys
    pm_raw = raw.get("pm")
    if not isinstance(pm_raw, dict):
        pm_raw = raw.get("particulate_matter")
    if not isinstance(pm_raw, dict):
        pm_raw = {}

    def _find_pm_val(keys):
        for k in keys:
            if k in pm_raw and pm_raw[k] is not None:
                return pm_raw[k]
        for k in keys:
            if k in raw and raw[k] is not None:
                return raw[k]
        return None

    pm1_0 = safe_float(_find_pm_val(["PM1_0", "pm1_0", "PM1.0", "pm1.0", "PM1", "pm1"]), default=0.0)
    pm2_5 = safe_float(_find_pm_val(["PM2_5", "pm2_5", "PM2.5", "pm2.5", "PM25", "pm25"]), default=0.0)
    pm10 = safe_float(_find_pm_val(["PM10", "pm10", "PM_10", "pm_10", "PM.10"]), default=0.0)
    pm = {"PM1_0": pm1_0, "PM2_5": pm2_5, "PM10": pm10}

    # If AQI was omitted/None but valid PM readings exist, auto-calculate EPA AQI
    if aqi_val is None and (pm2_5 > 0.0 or pm10 > 0.0):
        aqi_val = calculate_epa_aqi(pm2_5, pm10)

    # Predictions
    predictions_raw = raw.get("predictions")
    if not isinstance(predictions_raw, dict):
        predictions_raw = {}

    src_pred = "unknown"
    src_conf = None
    if "source" in predictions_raw and isinstance(predictions_raw["source"], dict):
        src_val = predictions_raw["source"].get("value")
        if src_val is not None:
            src_pred = str(src_val)
        src_conf = safe_float(predictions_raw["source"].get("confidence"), default=None)
    elif raw.get("source_prediction"):
        src_pred = str(raw.get("source_prediction"))
        src_conf = safe_float(raw.get("source_confidence"), default=None)

    # Advisory
    advisory_raw = raw.get("advisory")
    if not isinstance(advisory_raw, dict):
        advisory_raw = {}

    target_ip = ip or raw.get("ip")
    target_port = port or raw.get("port")
    try:
        if target_port is not None:
            target_port = int(target_port)
    except (ValueError, TypeError):
        target_port = None

    return {
        "node_id": target_node_id,
        "location": str(loc),
        "ip": str(target_ip) if target_ip else None,
        "port": target_port,
        "status": "active",
        "last_seen": ts,
        "aqi": aqi_val,
        "pm": pm,
        "temperature_C": temp_c,
        "humidity_pct": hum_pct,
        "source_prediction": src_pred,
        "source_confidence": src_conf,
        "predictions": predictions_raw,
        "advisory": advisory_raw,
    }


class ManagerService:
    def __init__(self, storage: Optional[ManagerStorage] = None):
        self.storage = storage or ManagerStorage()
        self.nodes: Dict[str, dict] = {}
        self.subscribers: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()
        self.uno_q_ip = os.getenv("NAVOS_UNO_Q_IP", os.getenv("UNO_Q_HOST_DEFAULT", "127.0.0.1")).strip()
        try:
            self.uno_q_port = int(os.getenv("NAVOS_UNO_Q_PORT", "8420"))
        except (ValueError, TypeError):
            self.uno_q_port = 8420
        self.uno_q_base_url = os.getenv("NAVOS_UNO_Q_URL", f"http://{self.uno_q_ip}:{self.uno_q_port}").rstrip("/")
        self.last_poll_successful = False
        self._load_initial_state()

    def _load_initial_state(self):
        """Restores state from storage on startup. Drops stale duplicate nodes not seen recently."""
        stored = self.storage.load_state()
        now_dt = datetime.now(timezone.utc)
        for node_id, state in stored.items():
            last_seen_raw = state.get("last_seen")
            is_stale = False
            if last_seen_raw:
                try:
                    dt = datetime.fromisoformat(last_seen_raw)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    if (now_dt - dt).total_seconds() > 900:
                        is_stale = True
                except Exception:
                    is_stale = True
            else:
                is_stale = True

            if not is_stale:
                state["status"] = "inactive"
                self.nodes[node_id] = state
            else:
                logger.info("Discarding stale duplicate node %s on startup (inactive > 15m)", node_id)

        if len(self.nodes) != len(stored):
            self.storage.save_state(self.nodes)
        logger.info("Manager Service initialized with %d active/recent nodes from storage.", len(self.nodes))

    def get_ip_config(self) -> Dict[str, Any]:
        """Returns the current edge node IP configuration details."""
        detected = None
        try:
            from scripts.update_env_ip import detect_network_ip
            detected = detect_network_ip()
        except Exception:
            pass

        from .config import UNO_Q_POLL_INTERVAL_S
        curr_url = os.getenv("NAVOS_UNO_Q_URL", self.uno_q_base_url).rstrip("/")
        curr_ip = os.getenv("NAVOS_UNO_Q_IP", self.uno_q_ip)
        try:
            curr_port = int(os.getenv("NAVOS_UNO_Q_PORT", str(self.uno_q_port)))
        except (ValueError, TypeError):
            curr_port = 8420

        poll_enabled = os.getenv("NAVOS_POLL_ENABLED", "true").lower() in ("true", "1", "yes")
        active_cnt = sum(1 for n in self.nodes.values() if n.get("status") == "active")

        return {
            "current_ip": curr_ip,
            "port": curr_port,
            "base_url": curr_url,
            "detected_local_ip": detected,
            "poll_enabled": poll_enabled,
            "poll_interval_s": UNO_Q_POLL_INTERVAL_S,
            "reachable": self.last_poll_successful,
            "active_nodes": active_cnt,
        }

    async def update_ip_config(
        self,
        ip: str,
        port: Optional[int] = None,
        poll_enabled: Optional[bool] = None,
        node_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Updates UNO Q IP address & port dynamically, persists to .env,
        triggers an immediate poll, and broadcasts SSE updates.
        """
        clean_ip = ip.strip()
        # Parse http:// prefix or host:port if user pasted a URL
        if clean_ip.startswith("http://") or clean_ip.startswith("https://"):
            from urllib.parse import urlparse
            parsed = urlparse(clean_ip)
            clean_ip = parsed.hostname or clean_ip
            if parsed.port and port is None:
                port = parsed.port
        elif ":" in clean_ip and not clean_ip.endswith(":"):
            parts = clean_ip.split(":", 1)
            clean_ip = parts[0].strip()
            if port is None:
                try:
                    port = int(parts[1].strip())
                except ValueError:
                    pass

        target_port = port if port is not None else self.uno_q_port
        from .config import set_uno_q_config
        new_url = set_uno_q_config(clean_ip, target_port, poll_enabled=poll_enabled, persist_env=True)
        self.uno_q_ip = clean_ip
        self.uno_q_port = target_port
        self.uno_q_base_url = new_url

        # Update node state in memory and storage if node_id matches
        async with self._lock:
            if node_id and node_id in self.nodes:
                self.nodes[node_id]["ip"] = clean_ip
                self.nodes[node_id]["port"] = target_port
                self.storage.save_state(self.nodes)
            elif len(self.nodes) == 1:
                first_node = next(iter(self.nodes.values()))
                first_node["ip"] = clean_ip
                first_node["port"] = target_port
                self.storage.save_state(self.nodes)

        # Trigger immediate poll to test connectivity
        overview = await self.poll_uno_q()

        config_data = self.get_ip_config()
        await self.broadcast_event("config_update", config_data)
        if node_id and node_id in self.nodes:
            await self.broadcast_event("node_status_change", self.get_node(node_id).model_dump())

        return {
            "success": True,
            "message": f"IP configuration updated to {clean_ip}:{target_port}",
            "current_ip": clean_ip,
            "port": target_port,
            "base_url": new_url,
            "detected_local_ip": config_data.get("detected_local_ip"),
            "poll_enabled": config_data.get("poll_enabled", True),
            "poll_interval_s": config_data.get("poll_interval_s", 36.0),
            "reachable": self.last_poll_successful,
            "active_nodes": overview.active_nodes,
        }

    async def register_node(self, node_id: str, location: Optional[str] = None, ip: Optional[str] = None) -> NodeState:
        async with self._lock:
            if node_id not in self.nodes:
                loc = location or DEFAULT_LOCATIONS.get(node_id, f"Location-{node_id}")
                self.nodes[node_id] = {
                    "node_id": node_id,
                    "location": loc,
                    "status": "active",
                    "last_seen": datetime.now(timezone.utc).isoformat(),
                    "aqi": None,
                    "pm": {"PM1_0": 0.0, "PM2_5": 0.0, "PM10": 0.0},
                    "temperature_C": 0.0,
                    "humidity_pct": 0.0,
                    "source_prediction": "unknown",
                    "source_confidence": None,
                    "predictions": {},
                    "advisory": {},
                }
            elif location:
                self.nodes[node_id]["location"] = location

            self.storage.save_state(self.nodes)
            state = self._get_node_state_model(node_id)
        
        await self.broadcast_event("node_registered", state.model_dump())
        return state

    async def ingest_telemetry(
        self,
        payload: Union[NodeTelemetryPayload, Dict[str, Any]],
        node_id: Optional[str] = None,
        ip: Optional[str] = None,
        port: Optional[int] = None,
    ) -> NodeState:
        normalized = normalize_telemetry(payload, node_id=node_id, ip=ip, port=port)
        target_node_id = normalized["node_id"]

        async with self._lock:
            # Preserve existing custom location if incoming payload omitted location
            if target_node_id in self.nodes:
                existing = self.nodes[target_node_id]
                has_explicit_loc = False
                if isinstance(payload, NodeTelemetryPayload) and payload.location:
                    has_explicit_loc = True
                elif isinstance(payload, dict) and payload.get("location"):
                    has_explicit_loc = True
                if not has_explicit_loc and existing.get("location"):
                    normalized["location"] = existing["location"]
                if not normalized.get("ip") and existing.get("ip"):
                    normalized["ip"] = existing["ip"]
                if not normalized.get("port") and existing.get("port"):
                    normalized["port"] = existing["port"]

            self.nodes[target_node_id] = normalized
            self.storage.save_state(self.nodes)
            state = self._get_node_state_model(target_node_id)

        await self.broadcast_event("telemetry_update", state.model_dump())
        return state

    def _get_node_state_model(self, node_id: str) -> NodeState:
        data = self.nodes.get(node_id)
        if not data:
            raise KeyError(f"Node {node_id} not found")

        last_seen_raw = data.get("last_seen")
        try:
            last_seen_dt = datetime.fromisoformat(last_seen_raw) if last_seen_raw else datetime.now(timezone.utc)
            if last_seen_dt.tzinfo is None:
                last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            last_seen_dt = datetime.now(timezone.utc)

        now_dt = datetime.now(timezone.utc)
        elapsed = max(0.0, (now_dt - last_seen_dt).total_seconds())

        pm_data = data.get("pm", {})
        if not isinstance(pm_data, dict):
            pm_data = {}

        return NodeState(
            node_id=data.get("node_id", node_id),
            location=data.get("location", f"Location-{node_id}"),
            ip=data.get("ip"),
            port=data.get("port"),
            status=data.get("status", "active"),
            last_seen=last_seen_dt.isoformat(),
            last_updated_seconds_ago=round(elapsed, 1),
            aqi=safe_float(data.get("aqi"), default=None),
            pm={
                "PM1_0": safe_float(pm_data.get("PM1_0"), default=0.0),
                "PM2_5": safe_float(pm_data.get("PM2_5"), default=0.0),
                "PM10": safe_float(pm_data.get("PM10"), default=0.0),
            },
            temperature_C=safe_float(data.get("temperature_C"), default=0.0),
            humidity_pct=safe_float(data.get("humidity_pct"), default=0.0),
            source_prediction=data.get("source_prediction", "unknown"),
            source_confidence=safe_float(data.get("source_confidence"), default=None),
            predictions=data.get("predictions", {}) if isinstance(data.get("predictions"), dict) else {},
            advisory=data.get("advisory", {}) if isinstance(data.get("advisory"), dict) else {},
        )

    def get_node(self, node_id: str) -> Optional[NodeState]:
        if node_id not in self.nodes:
            return None
        return self._get_node_state_model(node_id)

    async def remove_node(self, node_id: str) -> bool:
        """Removes a specific node from memory and storage."""
        async with self._lock:
            if node_id in self.nodes:
                del self.nodes[node_id]
                self.storage.save_state(self.nodes)
                removed = True
            else:
                removed = False

        if removed:
            await self.broadcast_event("node_status_change", self.get_overview().model_dump())
        return removed

    async def prune_inactive_nodes(self, keep_active_only: bool = True) -> List[str]:
        """
        Removes inactive or duplicate nodes that are not currently sending data.
        Keeps only the node(s) actively reporting.
        """
        removed = []
        async with self._lock:
            active_ids = {nid for nid, d in self.nodes.items() if d.get("status") == "active"}
            for nid, d in list(self.nodes.items()):
                # If there is at least one active node, remove all other inactive nodes
                # Or if the node is inactive, remove it
                if d.get("status") == "inactive" or (active_ids and nid not in active_ids):
                    del self.nodes[nid]
                    removed.append(nid)

            if removed:
                self.storage.save_state(self.nodes)

        if removed:
            await self.broadcast_event("node_status_change", self.get_overview().model_dump())
        return removed

    def list_nodes(self, active_only: bool = False) -> List[NodeState]:
        if active_only:
            return [self._get_node_state_model(nid) for nid, d in self.nodes.items() if d.get("status") == "active"]
        return [self._get_node_state_model(nid) for nid in self.nodes.keys()]

    def get_overview(self) -> OverviewResponse:
        nodes_list = self.list_nodes()
        active_nodes = [n for n in nodes_list if n.status == "active"]
        inactive_nodes = [n for n in nodes_list if n.status == "inactive"]

        stat_nodes = active_nodes if active_nodes else nodes_list

        if not stat_nodes:
            overall = OverallData(
                aqi=None,
                PM1_0=0.0,
                PM2_5=0.0,
                PM10=0.0,
                temperature_C=0.0,
                humidity_pct=0.0,
            )
        else:
            # Overall AQI: Max AQI among valid reporting nodes
            valid_aqis = [n.aqi for n in stat_nodes if n.aqi is not None]
            overall_aqi = round(max(valid_aqis), 1) if valid_aqis else None

            # Average PM levels across reporting nodes
            avg_pm1_0 = round(sum(safe_float(n.pm.get("PM1_0"), 0.0) for n in stat_nodes) / len(stat_nodes), 1)
            avg_pm2_5 = round(sum(safe_float(n.pm.get("PM2_5"), 0.0) for n in stat_nodes) / len(stat_nodes), 1)
            avg_pm10 = round(sum(safe_float(n.pm.get("PM10"), 0.0) for n in stat_nodes) / len(stat_nodes), 1)

            # Average Temperature and Humidity across reporting nodes
            avg_temp = round(sum(safe_float(n.temperature_C, 0.0) for n in stat_nodes) / len(stat_nodes), 1)
            avg_hum = round(sum(safe_float(n.humidity_pct, 0.0) for n in stat_nodes) / len(stat_nodes), 1)

            overall = OverallData(
                aqi=overall_aqi,
                PM1_0=avg_pm1_0,
                PM2_5=avg_pm2_5,
                PM10=avg_pm10,
                temperature_C=avg_temp,
                humidity_pct=avg_hum,
            )

        return OverviewResponse(
            active_nodes=len(active_nodes),
            inactive_nodes=len(inactive_nodes),
            total_nodes=len(nodes_list),
            overall=overall,
            nodes=nodes_list,
        )

    async def check_node_timeouts(self):
        """Background loop to detect and flag inactive/disconnected nodes."""
        status_changed = False
        async with self._lock:
            now_dt = datetime.now(timezone.utc)
            for node_id, data in list(self.nodes.items()):
                try:
                    if not isinstance(data, dict):
                        logger.warning("Invalid node state format for %s, skipping timeout check", node_id)
                        continue
                    if data.get("status") == "active":
                        last_seen_raw = data.get("last_seen")
                        if not last_seen_raw:
                            data["status"] = "inactive"
                            status_changed = True
                            continue
                        try:
                            last_seen_dt = datetime.fromisoformat(last_seen_raw)
                        except (ValueError, TypeError) as parse_err:
                            logger.warning("Unparseable last_seen '%s' for node %s: %s", last_seen_raw, node_id, parse_err)
                            data["status"] = "inactive"
                            status_changed = True
                            continue

                        if last_seen_dt.tzinfo is None:
                            last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)
                        elapsed = (now_dt - last_seen_dt).total_seconds()
                        if elapsed > INACTIVE_TIMEOUT_SECONDS:
                            logger.info("Node %s inactive (no data for %.1fs > threshold %ds)", node_id, elapsed, INACTIVE_TIMEOUT_SECONDS)
                            data["status"] = "inactive"
                            status_changed = True
                except Exception as node_err:
                    logger.error("Error checking timeout for node %s: %s", node_id, node_err, exc_info=True)

            if status_changed:
                self.storage.save_state(self.nodes)

        if status_changed:
            overview = self.get_overview()
            await self.broadcast_event("node_status_change", overview.model_dump())

    async def poll_uno_q(self) -> OverviewResponse:
        """
        Polls the configured UNO Q Intelligence Server endpoints over HTTP.
        Discovers active nodes on UNO Q and fetches latest intelligence data.
        If UNO Q is unreachable, marks active nodes as inactive cleanly without crashing.
        Survives individual node failures and malformed data.
        """
        from .config import UNO_Q_BASE_URL, UNO_Q_POLL_ENABLED

        base_url = os.getenv("NAVOS_UNO_Q_URL", getattr(self, "uno_q_base_url", UNO_Q_BASE_URL)).rstrip("/")
        poll_enabled_env = os.getenv("NAVOS_POLL_ENABLED")
        if poll_enabled_env is not None:
            poll_enabled = poll_enabled_env.lower() in ("true", "1", "yes")
        else:
            poll_enabled = UNO_Q_POLL_ENABLED

        if not poll_enabled or not base_url:
            return self.get_overview()

        logger.info("Polling UNO Q Intelligence Server at %s", base_url)
        try:
            import httpx
            async with httpx.AsyncClient(timeout=5.0) as client:
                try:
                    resp = await client.get(f"{base_url}/api/v1/nodes")
                except Exception as e:
                    logger.warning("Connection failure polling UNO Q at %s: %s", base_url, e)
                    self.last_poll_successful = False
                    await self.mark_uno_q_nodes_inactive()
                    return self.get_overview()

                if resp.status_code != 200:
                    logger.warning("UNO Q at %s returned HTTP status %d for /api/v1/nodes", base_url, resp.status_code)
                    self.last_poll_successful = False
                    await self.mark_uno_q_nodes_inactive()
                    return self.get_overview()

                try:
                    nodes_data = resp.json()
                except Exception as e:
                    logger.warning("Malformed JSON from UNO Q /api/v1/nodes at %s: %s", base_url, e)
                    self.last_poll_successful = False
                    await self.mark_uno_q_nodes_inactive()
                    return self.get_overview()

                if not isinstance(nodes_data, dict):
                    logger.warning("Unexpected response structure from UNO Q /api/v1/nodes: expected dict, got %s", type(nodes_data))
                    return self.get_overview()

                self.last_poll_successful = True
                nodes_list = nodes_data.get("nodes", [])
                if not isinstance(nodes_list, list) or not nodes_list:
                    logger.info("No active nodes reported by UNO Q at %s", base_url)
                    return self.get_overview()

                # Automatically prune stale duplicate nodes not reported by the connected UNO Q
                active_reported_ids = {
                    n_info.get("node_id") for n_info in nodes_list
                    if isinstance(n_info, dict) and n_info.get("node_id")
                }
                async with self._lock:
                    now_dt = datetime.now(timezone.utc)
                    stale_ids = []
                    for nid, node_data in list(self.nodes.items()):
                        if nid in active_reported_ids:
                            continue
                        # Prune any node not reported by UNO Q that is inactive or hasn't sent data in > 60s
                        last_seen_raw = node_data.get("last_seen")
                        is_fresh = False
                        if last_seen_raw and node_data.get("status") == "active":
                            try:
                                dt = datetime.fromisoformat(last_seen_raw)
                                if dt.tzinfo is None:
                                    dt = dt.replace(tzinfo=timezone.utc)
                                if (now_dt - dt).total_seconds() < 60:
                                    is_fresh = True
                            except Exception:
                                pass
                        if not is_fresh:
                            stale_ids.append(nid)

                    for s_id in stale_ids:
                        logger.info("Pruning stale duplicate/inactive node %s not in active UNO Q list", s_id)
                        del self.nodes[s_id]
                    if stale_ids:
                        self.storage.save_state(self.nodes)

                for n_info in nodes_list:
                    if not isinstance(n_info, dict):
                        logger.warning("Skipping invalid node info: %s", n_info)
                        continue

                    node_id = n_info.get("node_id")
                    if not node_id:
                        continue

                    try:
                        latest_resp = await client.get(f"{base_url}/api/v1/nodes/{node_id}/latest")
                        if latest_resp.status_code == 200:
                            try:
                                intel_data = latest_resp.json()
                            except Exception as json_err:
                                logger.error("Malformed JSON in /latest response for node %s: %s", node_id, json_err)
                                continue

                            if not isinstance(intel_data, dict):
                                logger.error("Invalid /latest response format for node %s: expected dict, got %s", node_id, type(intel_data))
                                continue

                            await self.ingest_telemetry(
                                intel_data,
                                node_id=node_id,
                                ip=getattr(self, "uno_q_ip", None),
                                port=getattr(self, "uno_q_port", None),
                            )
                            logger.info("Successfully ingested latest data for node %s from UNO Q (%s)", node_id, base_url)
                        elif latest_resp.status_code == 404:
                            logger.info("UNO Q node %s is registered but has no readings available yet.", node_id)
                        else:
                            logger.warning("UNO Q node %s /latest returned HTTP status %d", node_id, latest_resp.status_code)
                    except (httpx.RequestError, httpx.HTTPError) as node_http_err:
                        logger.error("HTTP error polling node %s /latest: %s", node_id, node_http_err)
                    except Exception as node_err:
                        logger.error("Error processing node %s during poll: %s", node_id, node_err, exc_info=True)

        except Exception as e:
            logger.error("Unexpected error in poll_uno_q: %s", e, exc_info=True)

        return self.get_overview()

    async def mark_uno_q_nodes_inactive(self):
        """Marks active nodes as inactive when UNO Q cannot be reached."""
        status_changed = False
        async with self._lock:
            for node_id, data in self.nodes.items():
                if data.get("status") == "active":
                    logger.info("Marking node %s inactive due to unreachable UNO Q server.", node_id)
                    data["status"] = "inactive"
                    status_changed = True

            if status_changed:
                self.storage.save_state(self.nodes)

        if status_changed:
            overview = self.get_overview()
            await self.broadcast_event("node_status_change", overview.model_dump())

    async def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self.subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue):
        async with self._lock:
            self.subscribers.discard(queue)

    async def broadcast_event(self, event_type: str, data: dict):
        if not self.subscribers:
            return
        
        message = f"event: {event_type}\ndata: {OverviewResponse.model_validate(self.get_overview()).model_dump_json()}\n\n"
        
        async with self._lock:
            for queue in list(self.subscribers):
                try:
                    queue.put_nowait(message)
                except asyncio.QueueFull:
                    pass
