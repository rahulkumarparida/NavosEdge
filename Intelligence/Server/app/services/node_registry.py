import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class NodeInfo:
    node_id: str
    first_seen: datetime
    last_seen: datetime
    total_readings: int
    status: str


class NodeRegistry:
    def __init__(self) -> None:
        self._nodes: Dict[str, NodeInfo] = {}
        self._lock = threading.Lock()

    def register_reading(self, node_id: str, timestamp: datetime) -> NodeInfo:
        with self._lock:
            if node_id in self._nodes:
                node = self._nodes[node_id]
                node.last_seen = timestamp
                node.total_readings += 1
                node.status = "active"
                return node
            
            node = NodeInfo(
                node_id=node_id,
                first_seen=timestamp,
                last_seen=timestamp,
                total_readings=1,
                status="active",
            )
            self._nodes[node_id] = node
            return node

    def get_node(self, node_id: str) -> Optional[NodeInfo]:
        with self._lock:
            return self._nodes.get(node_id)

    def list_nodes(self) -> List[NodeInfo]:
        with self._lock:
            return list(self._nodes.values())

    def has_node(self, node_id: str) -> bool:
        with self._lock:
            return node_id in self._nodes
