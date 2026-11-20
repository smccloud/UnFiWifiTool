from __future__ import annotations

from fastapi import Request

from app.unifi.service import UniFiService


def get_service(request: Request) -> UniFiService:
    return request.app.state.unifi


def get_request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)
