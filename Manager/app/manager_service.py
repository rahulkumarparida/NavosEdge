"""
Core Manager Service — Node Tracking, Aggregation & SSE Event Distribution
"""

import asyncio
from datetime import datetime, timezone
import logging
from typing import Dict, List, Optional, Set
from pydantic import BaseModel

from app.config import DEFAULT_LOCATIONS, INACTIVE_TIMEOUT_SECONDS
from app.models import NodeState, NodeTelemetryPayload, OverallData, OverviewResponse
from app.storage import ManagerStorage

logger = logging.getLogger(__name__)


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
        now_iso = datetime.now(timezone.utc).isoformat()
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

    async def ingest_telemetry(self, payload: NodeTelemetryPayload) -> NodeState:
        async with self._lock:
            node_id = payload.node_id
            now_iso = payload.timestamp or datetime.now(timezone.utc).isoformat()
            location = payload.location or DEFAULT_LOCATIONS.get(node_id, f"Location-{node_id}")

            # Parse predictions
            src_pred = "unknown"
            src_conf = None
            predictions_raw = payload.predictions or {}
            if "source" in predictions_raw and isinstance(predictions_raw["source"], dict):
                src_pred = predictions_raw["source"].get("value", "unknown")
                src_conf = predictions_raw["source"].get("confidence", None)

            # Parse PM
            pm = payload.pm or {}
            pm1_0 = float(pm.get("PM1_0", pm.get("pm1_0", 0.0)))
            pm2_5 = float(pm.get("PM2_5", pm.get("pm2_5", 0.0)))
            pm10 = float(pm.get("PM10", pm.get("pm10", 0.0)))

            node_data = {
                "node_id": node_id,
                "location": location,
                "status": "active",
                "last_seen": now_iso,
                "aqi": payload.aqi,
                "pm": {"PM1_0": pm1_0, "PM2_5": pm2_5, "PM10": pm10},
                "temperature_C": float(payload.temperature_C),
                "humidity_pct": float(payload.humidity_pct),
                "source_prediction": src_pred,
                "source_confidence": src_conf,
                "predictions": predictions_raw,
                "advisory": payload.advisory or {},
            }

            self.nodes[node_id] = node_data
            self.storage.save_state(self.nodes)
            state = self._get_node_state_model(node_id)

        await self.broadcast_event("telemetry_update", state.model_dump())
        return state

    def _get_node_state_model(self, node_id: str) -> NodeState:
        data = self.nodes.get(node_id)
        if not data:
            raise KeyError(f"Node {node_id} not found")

        # Calculate last updated seconds ago
        last_seen_dt = datetime.fromisoformat(data["last_seen"])
        if last_seen_dt.tzinfo is None:
            last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)
        now_dt = datetime.now(timezone.utc)
        elapsed = max(0.0, (now_dt - last_seen_dt).total_seconds())

        return NodeState(
            node_id=data["node_id"],
            location=data["location"],
            status=data["status"],
            last_seen=data["last_seen"],
            last_updated_seconds_ago=round(elapsed, 1),
            aqi=data.get("aqi"),
            pm=data.get("pm", {}),
            temperature_C=data.get("temperature_C", 0.0),
            humidity_pct=data.get("humidity_pct", 0.0),
            source_prediction=data.get("source_prediction", "unknown"),
            source_confidence=data.get("source_confidence"),
            predictions=data.get("predictions", {}),
            advisory=data.get("advisory", {}),
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
            avg_pm1_0 = round(sum(n.pm.get("PM1_0", 0.0) for n in active_nodes) / len(active_nodes), 1)
            avg_pm2_5 = round(sum(n.pm.get("PM2_5", 0.0) for n in active_nodes) / len(active_nodes), 1)
            avg_pm10 = round(sum(n.pm.get("PM10", 0.0) for n in active_nodes) / len(active_nodes), 1)

            # Average Temperature and Humidity across active nodes
            avg_temp = round(sum(n.temperature_C for n in active_nodes) / len(active_nodes), 1)
            avg_hum = round(sum(n.humidity_pct for n in active_nodes) / len(active_nodes), 1)

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
            for node_id, data in self.nodes.items():
                if data["status"] == "active":
                    last_seen_dt = datetime.fromisoformat(data["last_seen"])
                    if last_seen_dt.tzinfo is None:
                        last_seen_dt = last_seen_dt.replace(tzinfo=timezone.utc)
                    elapsed = (now_dt - last_seen_dt).total_seconds()
                    if elapsed > INACTIVE_TIMEOUT_SECONDS:
                        logger.info("Node %s inactive (no data for %.1fs > threshold %ds)", node_id, elapsed, INACTIVE_TIMEOUT_SECONDS)
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
