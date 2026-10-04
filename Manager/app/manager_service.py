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


def normalize_telemetry(
    payload: Union[NodeTelemetryPayload, Dict[str, Any], Any],
    node_id: Optional[str] = None,
    default_location: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Unified normalization for telemetry from both Push (HTTP POST)
    and Pull (UNO Q /latest polling) paths.

    Guarantees consistent Manager node state:
    - Missing or null temperature_C / humidity_pct safely normalize to 0.0.
    - Legitimate 0, 0.0, and valid negative values are preserved.
    - aqi is preserved if present (including 0.0), or None if missing/null.
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

    # Environmental: temperature_C and humidity_pct
    temp_c = safe_float(raw.get("temperature_C"), default=0.0)
    hum_pct = safe_float(raw.get("humidity_pct"), default=0.0)

    # AQI: optional, preserve None if absent or null
    aqi_val = safe_float(raw.get("aqi"), default=None)

    # PM readings
    pm_raw = raw.get("pm")
    if not isinstance(pm_raw, dict):
        pm_raw = {}
    pm1_0 = safe_float(pm_raw.get("PM1_0") if "PM1_0" in pm_raw else pm_raw.get("pm1_0"), default=0.0)
    pm2_5 = safe_float(pm_raw.get("PM2_5") if "PM2_5" in pm_raw else pm_raw.get("pm2_5"), default=0.0)
    pm10 = safe_float(pm_raw.get("PM10") if "PM10" in pm_raw else pm_raw.get("pm10"), default=0.0)
    pm = {"PM1_0": pm1_0, "PM2_5": pm2_5, "PM10": pm10}

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

    return {
        "node_id": target_node_id,
        "location": str(loc),
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
        self._load_initial_state()

    def _load_initial_state(self):
        """Restores state from storage on startup."""
        stored = self.storage.load_state()
        for node_id, state in stored.items():
            # Mark all restored nodes as inactive until a new reading arrives or timeout check runs
            state["status"] = "inactive"
            self.nodes[node_id] = state
        logger.info("Manager Service initialized with %d nodes from storage.", len(self.nodes))

    async def register_node(self, node_id: str, location: Optional[str] = None) -> NodeState:
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
    ) -> NodeState:
        normalized = normalize_telemetry(payload, node_id=node_id)
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

    def list_nodes(self) -> List[NodeState]:
        return [self._get_node_state_model(nid) for nid in self.nodes.keys()]

    def get_overview(self) -> OverviewResponse:
        nodes_list = self.list_nodes()
        active_nodes = [n for n in nodes_list if n.status == "active"]
        inactive_nodes = [n for n in nodes_list if n.status == "inactive"]

        if not active_nodes:
            overall = OverallData(
                aqi=None,
                PM1_0=0.0,
                PM2_5=0.0,
                PM10=0.0,
                temperature_C=0.0,
                humidity_pct=0.0,
            )
        else:
            # Overall AQI: Max AQI among active nodes (as per EPA/CPCB multi-station regional AQI standard)
            valid_aqis = [n.aqi for n in active_nodes if n.aqi is not None]
            overall_aqi = round(max(valid_aqis), 1) if valid_aqis else None

            # Average PM levels across active nodes
            avg_pm1_0 = round(sum(safe_float(n.pm.get("PM1_0"), 0.0) for n in active_nodes) / len(active_nodes), 1)
            avg_pm2_5 = round(sum(safe_float(n.pm.get("PM2_5"), 0.0) for n in active_nodes) / len(active_nodes), 1)
            avg_pm10 = round(sum(safe_float(n.pm.get("PM10"), 0.0) for n in active_nodes) / len(active_nodes), 1)

            # Average Temperature and Humidity across active nodes
            avg_temp = round(sum(safe_float(n.temperature_C, 0.0) for n in active_nodes) / len(active_nodes), 1)
            avg_hum = round(sum(safe_float(n.humidity_pct, 0.0) for n in active_nodes) / len(active_nodes), 1)

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
        from app.config import UNO_Q_BASE_URL, UNO_Q_POLL_ENABLED

        base_url = os.getenv("NAVOS_UNO_Q_URL", UNO_Q_BASE_URL).rstrip("/")
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
                    await self.mark_uno_q_nodes_inactive()
                    return self.get_overview()

                if resp.status_code != 200:
                    logger.warning("UNO Q at %s returned HTTP status %d for /api/v1/nodes", base_url, resp.status_code)
                    await self.mark_uno_q_nodes_inactive()
                    return self.get_overview()

                try:
                    nodes_data = resp.json()
                except Exception as e:
                    logger.warning("Malformed JSON from UNO Q /api/v1/nodes at %s: %s", base_url, e)
                    await self.mark_uno_q_nodes_inactive()
                    return self.get_overview()

                if not isinstance(nodes_data, dict):
                    logger.warning("Unexpected response structure from UNO Q /api/v1/nodes: expected dict, got %s", type(nodes_data))
                    return self.get_overview()

                nodes_list = nodes_data.get("nodes", [])
                if not isinstance(nodes_list, list) or not nodes_list:
                    logger.info("No active nodes reported by UNO Q at %s", base_url)
                    return self.get_overview()

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

                            await self.ingest_telemetry(intel_data, node_id=node_id)
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
