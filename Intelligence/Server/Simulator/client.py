"""HTTP client for the existing NavosEdge Intelligence API."""

from __future__ import annotations

import asyncio
import json
import logging
from urllib.parse import urlencode
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)


@dataclass
class ApiResult:
    ok: bool
    status_code: int | None
    body: dict | str | None
    error: str | None = None


class IntelligenceClient:
    """Small dependency-free async wrapper around the server's real routes."""

    def __init__(self, base_url: str = "http://127.0.0.1:8420", timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    async def health(self) -> ApiResult:
        return await self._request("GET", "/health")

    async def ready(self) -> ApiResult:
        return await self._request("GET", "/ready")

    async def submit(self, payload: dict) -> ApiResult:
        return await self._request("POST", f"/api/v1/nodes/{payload['node_id']}/readings", payload)

    async def status(self, node_id: str) -> ApiResult:
        return await self._request("GET", f"/api/v1/nodes/{node_id}/status")

    async def latest(self, node_id: str) -> ApiResult:
        return await self._request("GET", f"/api/v1/nodes/{node_id}/latest")

    async def forecast(
        self,
        node_id: str,
        horizon_minutes: int = 60,
        sampling_interval_minutes: int = 5,
    ) -> ApiResult:
        query = urlencode({
            "horizon_minutes": horizon_minutes,
            "sampling_interval_minutes": sampling_interval_minutes,
        })
        return await self._request("GET", f"/api/v1/forecast/nodes/{node_id}/predict?{query}")

    async def forecast_ingest(self, payload: dict) -> ApiResult:
        reading = {
            "node_id": payload["node_id"],
            "timestamp": payload["timestamp"],
            **payload["particulate_matter"],
            "is_synthetic": True,
        }
        return await self._request("POST", f"/api/v1/forecast/nodes/{payload['node_id']}/readings", reading)

    async def _request(self, method: str, path: str, body: dict | None = None) -> ApiResult:
        return await asyncio.to_thread(self._request_sync, method, path, body)

    def _request_sync(self, method: str, path: str, body: dict | None) -> ApiResult:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return ApiResult(True, response.status, _decode_body(raw))
        except HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            return ApiResult(False, exc.code, _decode_body(raw), f"HTTP {exc.code}")
        except (URLError, TimeoutError, OSError) as exc:
            return ApiResult(False, None, None, str(exc))
        except Exception as exc:  # pragma: no cover - defensive boundary
            logger.exception("Unexpected API client error")
            return ApiResult(False, None, None, str(exc))


def _decode_body(raw: str) -> dict | str | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw
