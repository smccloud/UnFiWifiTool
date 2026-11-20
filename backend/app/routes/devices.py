from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import audit
from app.auth import csrf_guard, require_user
from app.config import get_settings
from app.db import get_db
from app.deps import get_request_id, get_service
from app.models import Device
from app.reconcile import apply_device_now
from app.schedule import ScheduleError, clear_schedule, save_schedule, validate_schedule
from app.schemas import (
    DeviceCreate,
    DeviceList,
    DeviceOut,
    DeviceUpdate,
    ScheduleUpdate,
    device_out,
)
from app.unifi.errors import UniFiError
from app.unifi.service import UniFiService
from app.unifi.types import validate_device_mac

router = APIRouter(
    prefix="/api/devices",
    tags=["devices"],
    dependencies=[Depends(require_user), Depends(csrf_guard)],
)


def _get_device(db: Session, device_id: int) -> Device:
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return device


@router.get("", response_model=DeviceList)
def list_devices(
    q: str = "",
    access_mode: str = "",
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    query = db.query(Device)
    if q.strip():
        needle = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(Device.mac).like(needle),
                func.lower(Device.label).like(needle),
                func.lower(func.coalesce(Device.hostname, "")).like(needle),
                func.lower(func.coalesce(Device.notes, "")).like(needle),
            )
        )
    if access_mode:
        modes = {item.strip() for item in access_mode.split(",") if item.strip()}
        valid = {"allowed", "blocked", "scheduled", "ignored"}
        if modes - valid:
            raise HTTPException(status_code=400, detail="Invalid access_mode filter")
        query = query.filter(Device.access_mode.in_(modes))

    total = query.count()
    devices = (
        query.order_by(Device.updated_at.desc()).offset(offset).limit(limit).all()
    )
    return DeviceList(items=[device_out(device) for device in devices], total=total)


@router.get("/{device_id}", response_model=DeviceOut)
def get_device(device_id: int, db: Session = Depends(get_db)):
    return device_out(_get_device(db, device_id))


@router.post("", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
def create_device(
    payload: DeviceCreate,
    request: Request,
    db: Session = Depends(get_db),
    service: UniFiService = Depends(get_service),
    user: str = Depends(require_user),
):
    try:
        mac = validate_device_mac(payload.mac)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if db.query(Device).filter(Device.mac == mac).first():
        raise HTTPException(status_code=409, detail="A device with this MAC already exists")

    device = Device(
        mac=mac,
        label=payload.label.strip()[:128],
        notes=payload.notes.strip(),
        access_mode=payload.access_mode,
        source="manual",
        created_by=user,
        effective_access=payload.access_mode,
    )
    db.add(device)
    db.flush()
    audit.record(
        db,
        actor=user,
        action="device_added",
        target_mac=mac,
        detail={"accessMode": payload.access_mode},
        request_id=get_request_id(request),
    )
    db.commit()
    db.refresh(device)

    if payload.access_mode != "ignored":
        apply_device_now(
            db,
            service,
            get_settings(),
            device,
            actor=user,
            reason="device_created",
        )
        db.commit()
        db.refresh(device)

    return device_out(device)


@router.patch("/{device_id}", response_model=DeviceOut)
def update_device(
    device_id: int,
    payload: DeviceUpdate,
    request: Request,
    db: Session = Depends(get_db),
    service: UniFiService = Depends(get_service),
    user: str = Depends(require_user),
):
    device = _get_device(db, device_id)
    if payload.label is not None:
        device.label = payload.label.strip()[:128]
    if payload.notes is not None:
        device.notes = payload.notes.strip()

    mode_changed = False
    if payload.access_mode is not None and payload.access_mode != device.access_mode:
        previous = device.access_mode
        device.access_mode = payload.access_mode
        mode_changed = True
        if payload.access_mode != "scheduled":
            device.next_change_at = None
        audit.record(
            db,
            actor=user,
            action="access_changed",
            target_mac=device.mac,
            detail={"from": previous, "to": payload.access_mode},
            request_id=get_request_id(request),
        )
    db.commit()
    db.refresh(device)

    if mode_changed and payload.apply:
        apply_device_now(
            db,
            service,
            get_settings(),
            device,
            actor=user,
            reason="manual",
        )
        db.commit()
        db.refresh(device)

    return device_out(device)


@router.delete("/{device_id}")
def delete_device(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(require_user),
):
    device = _get_device(db, device_id)
    mac = device.mac
    label = device.label
    db.delete(device)
    audit.record(
        db,
        actor=user,
        action="device_removed",
        target_mac=mac,
        detail={"label": label, "note": "UniFi block state was not changed"},
        request_id=get_request_id(request),
    )
    db.commit()
    return {"ok": True, "mac": mac}


@router.post("/{device_id}/schedule", response_model=DeviceOut)
def set_schedule(
    device_id: int,
    payload: ScheduleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    service: UniFiService = Depends(get_service),
    user: str = Depends(require_user),
):
    device = _get_device(db, device_id)
    try:
        normalized = validate_schedule(payload.schedule.model_dump())
    except ScheduleError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    save_schedule(device, normalized)
    device.access_mode = "scheduled"
    audit.record(
        db,
        actor=user,
        action="schedule_set",
        target_mac=device.mac,
        detail=normalized,
        request_id=get_request_id(request),
    )
    db.commit()
    db.refresh(device)

    if payload.apply:
        apply_device_now(
            db,
            service,
            get_settings(),
            device,
            actor=user,
            reason="schedule_updated",
        )
        db.commit()
        db.refresh(device)

    return device_out(device)


@router.delete("/{device_id}/schedule", response_model=DeviceOut)
def remove_schedule(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: str = Depends(require_user),
):
    device = _get_device(db, device_id)
    clear_schedule(device)
    device.access_mode = "ignored"
    device.effective_access = "ignored"
    audit.record(
        db,
        actor=user,
        action="schedule_cleared",
        target_mac=device.mac,
        detail={"note": "Device is now unmanaged; UniFi block state was not changed"},
        request_id=get_request_id(request),
    )
    db.commit()
    db.refresh(device)
    return device_out(device)


@router.post("/{device_id}/apply", response_model=DeviceOut)
def apply_now(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
    service: UniFiService = Depends(get_service),
    user: str = Depends(require_user),
):
    device = _get_device(db, device_id)
    try:
        apply_device_now(
            db,
            service,
            get_settings(),
            device,
            actor=user,
            reason="manual_apply",
        )
    except UniFiError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.commit()
    db.refresh(device)
    return device_out(device)
