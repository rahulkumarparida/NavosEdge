import asyncio
import json
import logging
from typing import AsyncGenerator, Dict, List

logger = logging.getLogger(__name__)


class EventService:
    def __init__(self, heartbeat_interval: float = 15.0) -> None:
        self.heartbeat_interval = heartbeat_interval
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, node_id: str) -> AsyncGenerator[str, None]:
        queue: asyncio.Queue = asyncio.Queue()
        
        async with self._lock:
            if node_id not in self._subscribers:
                self._subscribers[node_id] = []
            self._subscribers[node_id].append(queue)

        try:
            yield "event: connected\ndata: {}\n\n"
            
            while True:
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=self.heartbeat_interval)
                    yield event_data
                except asyncio.TimeoutError:
                    yield ":heartbeat\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await self.disconnect(node_id, queue)

    async def publish(self, node_id: str, event_type: str, data: dict) -> int:
        event_str = f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
        
        async with self._lock:
            if node_id not in self._subscribers:
                return 0
            
            subscribers = self._subscribers[node_id]
            count = 0
            for queue in subscribers:
                queue.put_nowait(event_str)
                count += 1
                
            return count

    async def disconnect(self, node_id: str, queue: asyncio.Queue) -> None:
        async with self._lock:
            if node_id in self._subscribers:
                if queue in self._subscribers[node_id]:
                    self._subscribers[node_id].remove(queue)
                if not self._subscribers[node_id]:
                    del self._subscribers[node_id]
