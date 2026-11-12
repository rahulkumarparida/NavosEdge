"""
Lightweight Manager & Operator authorization dependencies for Phase 5.

- When `NAVOS_MANAGER_API_KEY` is configured, protected endpoints require a
  matching `X-Navos-Manager-Key` or `Authorization: Bearer <key>` header.
- Sensitive resident `safety_information` additionally requires explicit
  `X-Navos-Safety-Access: authorized` header.
- Webhook endpoints (`/api/v1/webhooks/twilio/*`) and signed ack links
  (`/api/v1/notifications/ack/{token}`) use their own cryptographic verification
  and are never exposed as ordinary manager actions.
"""

from __future__ import annotations

import hmac
from typing import Optional

from fastapi import HTTPException, Request, status


def _extract_provided_key(request: Request) -> Optional[str]:
    key = request.headers.get("X-Navos-Manager-Key")
    if key:
        return key.strip()
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def require_manager_auth(request: Request) -> str:
    """
    Verify manager/operator authorization when `NAVOS_MANAGER_API_KEY` is set.
    Returns the authenticated operator identifier (`X-Navos-Operator`).
    """
    settings = getattr(request.app.state, "settings", None)
    expected_key = getattr(settings, "MANAGER_API_KEY", None) if settings else None

    if expected_key:
        provided = _extract_provided_key(request)
        if not provided or not hmac.compare_digest(provided, expected_key):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Valid Manager API key required (X-Navos-Manager-Key or Bearer token)",
            )

    operator = request.headers.get("X-Navos-Operator", "").strip()
    return operator or "manager"


def require_safety_info_access(request: Request) -> None:
    """
    Restrict access to sensitive resident `safety_information` notes.
    """
    require_manager_auth(request)
    flag = request.headers.get("X-Navos-Safety-Access", "").strip().lower()
    if flag != "authorized":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Explicit safety-information access authorization header required (X-Navos-Safety-Access: authorized)",
        )

