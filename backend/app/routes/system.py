from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth import csrf_guard, require_user
from app.config import get_settings
from app.db import get_db
from app.deps import get_service
from app.models import Device
from app.reconcile import SyncBusy, run_sync
from app.runtime import get_setting
from app.schemas import ControllerInfo, Counts, StatusOut, SyncSummaryOut
from app.timeutil import utcnow
from app.unifi.errors import UniFiError
from app.unifi.service import UniFiService

router = APIRouter(
    prefix="/api/system",
    tags=["system"],
    dependencies=[Depends(require_user), Depends(csrf_guard)],
)


def _controller_info(service: UniFiService) -> ControllerInfo:
    status = service.detect()
    site = (
        {"id": status.site_id, "name": status.site_name}
        if status.site_id or status.site_name
        else None
    )
    return ControllerInfo(
        host=status.host,
        integration_ok=status.integration_ok,
        classic_ok=status.classic_ok,
        ssid_allowlist_ok=status.ssid_allowlist_ok,
        version=status.version,
        site=site,
        error=status.error,
        warnings=status.warnings,
        checked_at=status.checked_at,
    )


@router.get("/status", response_model=StatusOut)
def status(
    db: Session = Depends(get_db),
    service: UniFiService = Depends(get_service),
):
    settings = get_settings()
    controller = _controller_info(service)

    total = db.query(Device).count()
    counts = Counts(
        devices=total,
        allowed=db.query(Device).filter(Device.access_mode == "allowed").count(),
        blocked=db.query(Device).filter(Device.access_mode == "blocked").count(),
        scheduled=db.query(Device).filter(Device.access_mode == "scheduled").count(),
        ignored=db.query(Device).filter(Device.access_mode == "ignored").count(),
        connected=db.query(Device)
        .filter(Device.last_seen_at >= utcnow() - timedelta(minutes=10))
        .count(),
    )

    last_sync_raw = get_setting(db, "last_sync")
    last_sync = None
    if isinstance(last_sync_raw, dict):
        try:
            last_sync = SyncSummaryOut(**last_sync_raw)
        except (TypeError, ValueError):
            last_sync = None

    return StatusOut(
        app_name=settings.app_name,
        version="0.1.0",
        auth_disabled=settings.auth_disabled,
        timezone=settings.app_timezone,
        controller=controller,
        enforcement={
            "autoApply": settings.auto_apply,
            "dryRun": settings.dry_run,
            "schedulerEnabled": settings.scheduler_enabled,
            "intervalSeconds": settings.scheduler_interval_seconds,
            "discoveryEnabled": settings.discovery_enabled,
            "ssidAllowlistEnabled": settings.enable_ssid_allowlist,
            "mode": "block/unblock",
        },
        counts=counts,
        last_sync=last_sync,
        security_note=settings.security_note,
    )


@router.post("/sync", response_model=SyncSummaryOut)
def sync_now(
    request: Request,
    db: Session = Depends(get_db),
    service: UniFiService = Depends(get_service),
    user: str = Depends(require_user),
):
    try:
        summary = run_sync(db, service, get_settings(), actor=user)
    except SyncBusy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except UniFiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return SyncSummaryOut(**summary.to_dict())


@router.post("/test", response_model=ControllerInfo)
def test_connection(service: UniFiService = Depends(get_service)):
    service.invalidate()
    return _controller_info(service)
