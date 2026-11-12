"""
Reverse-proxy router forwarding Emergency, Resident, Contact, Actuator, and
Notification requests from the Manager SPA to the active UNO Q Intelligence
Server (`get_uno_q_base_url()`), avoiding any duplicate SQLite database or
parallel backend.

Webhook-only routes (`/api/v1/webhooks/*`) are intentionally excluded.
"""

from __future__ import annotations

import logging
from typing import Dict

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status
from starlette.responses import StreamingResponse

from app.config import get_uno_q_base_url

logger = logging.getLogger(__name__)

router = APIRouter(tags=["emergency-proxy"])

_FORWARDED_HEADERS = (
    "content-type",
    "authorization",
    "x-navos-manager-key",
    "x-navos-operator",
    "x-navos-safety-access",
)


def _extract_forward_headers(request: Request) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for name in _FORWARDED_HEADERS:
        val = request.headers.get(name)
        if val:
            headers[name] = val
    return headers


@router.get("/api/v1/emergency/stream")
async def proxy_emergency_sse(request: Request):
    """Stream real-time emergency SSE events from UNO Q Intelligence Server."""
    target_url = f"{get_uno_q_base_url()}/api/v1/emergency/stream"
    headers = _extract_forward_headers(request)

    async def stream_gen():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", target_url, headers=headers) as resp:
                    async for chunk in resp.aiter_bytes():
                        if await request.is_disconnected():
                            break
                        yield chunk
        except Exception as exc:
            logger.debug("Emergency SSE proxy disconnected: %s", exc)

    return StreamingResponse(
        stream_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _proxy_request(request: Request, upstream_path: str) -> Response:
    base_url = get_uno_q_base_url()
    url = f"{base_url}{upstream_path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    body = await request.body()
    headers = _extract_forward_headers(request)

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.request(
                method=request.method,
                url=url,
                headers=headers,
                content=body if body else None,
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"UNO Q Intelligence Server unreachable at {base_url}: {type(exc).__name__}",
        ) from exc

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        media_type=resp.headers.get("content-type", "application/json"),
    )


@router.api_route(
    "/api/v1/emergency/{subpath:path}",
    methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
)
async def proxy_emergency(subpath: str, request: Request):
    return await _proxy_request(request, f"/api/v1/emergency/{subpath}")


@router.api_route(
    "/api/v1/actuators",
    methods=["GET", "POST"],
)
async def proxy_actuators_root(request: Request):
    return await _proxy_request(request, "/api/v1/actuators")


@router.api_route(
    "/api/v1/actuators/{subpath:path}",
    methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
)
async def proxy_actuators(subpath: str, request: Request):
    return await _proxy_request(request, f"/api/v1/actuators/{subpath}")


@router.api_route(
    "/api/v1/notifications/{subpath:path}",
    methods=["GET", "POST"],
)
async def proxy_notifications(subpath: str, request: Request):
    return await _proxy_request(request, f"/api/v1/notifications/{subpath}")


@router.api_route(
    "/api/v1/events/{subpath:path}",
    methods=["GET", "POST"],
)
async def proxy_events(subpath: str, request: Request):
    return await _proxy_request(request, f"/api/v1/events/{subpath}")

