from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import AuditLog, Device
from app.schedule import Schedule, load_schedule, schedule_to_dict

AccessMode = Literal["allowed", "blocked", "scheduled", "ignored"]
EditableAccessMode = Literal["allowed", "blocked", "ignored"]
ScheduleKind = Literal["allow_during", "block_during"]


class ScheduleWindowIn(BaseModel):
    days: list[int] = Field(min_length=1)
    start: str
    end: str
    # Optional for legacy payloads; validate_schedule derives it from kind.
    action: Literal["allow", "block"] | None = None


class ScheduleWindowOut(BaseModel):
    days: list[int]
    start: str
    end: str
    action: Literal["allow", "block"]


class ScheduleIn(BaseModel):
    default_access: Literal["allowed", "blocked"] | None = None
    # Legacy clients may still send kind; validate_schedule converts it.
    kind: ScheduleKind | None = None
    timezone: str = "UTC"
    windows: list[ScheduleWindowIn] = Field(min_length=1)


class ScheduleOut(BaseModel):
    default_access: Literal["allowed", "blocked"]
    timezone: str
    windows: list[ScheduleWindowOut]


class DeviceCreate(BaseModel):
    mac: str
    label: str = ""
    notes: str = ""
    access_mode: EditableAccessMode = "allowed"


class DeviceUpdate(BaseModel):
    label: str | None = None
    notes: str | None = None
    access_mode: EditableAccessMode | None = None
    apply: bool = True


class ScheduleUpdate(BaseModel):
    schedule: ScheduleIn
    apply: bool = True


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mac: str
    label: str
    notes: str
    access_mode: AccessMode
    schedule: ScheduleOut | None = None
    effective_access: str | None = None
    next_change_at: datetime | None = None
    last_applied_access: str | None = None
    last_applied_at: datetime | None = None
    last_synced_at: datetime | None = None
    last_error: str | None = None
    observed_blocked: bool | None = None
    hostname: str | None = None
    ip_address: str | None = None
    last_ssid: str | None = None
    last_signal: int | None = None
    last_seen_at: datetime | None = None
    unifi_client_id: str | None = None
    source: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    connected: bool | None = None


class DeviceList(BaseModel):
    items: list[DeviceOut]
    total: int


class ClientOut(BaseModel):
    mac: str
    name: str | None = None
    hostname: str | None = None
    ip_address: str | None = None
    ssid: str | None = None
    signal: int | None = None
    blocked: bool | None = None
    connected: bool = True
    connection_type: str | None = None
    last_seen_at: datetime | None = None
    source: str
    device_id: int | None = None
    label: str | None = None
    access_mode: AccessMode | None = None
    effective_access: str | None = None
    managed: bool = False


class ClientList(BaseModel):
    items: list[ClientOut]
    connected_total: int
    managed_total: int


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    actor: str
    action: str
    target_mac: str | None = None
    result: str
    detail: dict | None = None
    request_id: str | None = None


class AuditList(BaseModel):
    items: list[AuditOut]
    total: int


class SyncSummaryOut(BaseModel):
    started_at: datetime
    finished_at: datetime
    discovered: int = 0
    updated: int = 0
    applied: int = 0
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)
    transitions: list[dict] = Field(default_factory=list)
    dry_run: bool = False


class ControllerInfo(BaseModel):
    host: str
    integration_ok: bool
    classic_ok: bool
    ssid_allowlist_ok: bool
    version: str | None = None
    site: dict | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    checked_at: datetime | None = None


class Counts(BaseModel):
    devices: int
    allowed: int
    blocked: int
    scheduled: int
    ignored: int
    connected: int


class StatusOut(BaseModel):
    app_name: str
    version: str
    auth_disabled: bool
    timezone: str
    controller: ControllerInfo
    enforcement: dict
    counts: Counts
    last_sync: SyncSummaryOut | None = None
    security_note: str | None = None


class WifiNetworkOut(BaseModel):
    id: str | None
    name: str | None
    enabled: bool | None = None
    type: str | None = None
    policy: dict


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    username: str
    csrf_token: str


class MeResponse(BaseModel):
    username: str
    csrf_token: str
    auth_disabled: bool
    app_name: str
    version: str


def schedule_out(schedule: Schedule) -> ScheduleOut:
    payload = schedule_to_dict(schedule)
    assert payload is not None
    return ScheduleOut(**payload)


def device_out(device: Device, connected: bool | None = None) -> DeviceOut:
    schedule = load_schedule(device) if device.access_mode == "scheduled" else None
    return DeviceOut(
        id=device.id,
        mac=device.mac,
        label=device.label or "",
        notes=device.notes or "",
        access_mode=device.access_mode,  # type: ignore[arg-type]
        schedule=schedule_out(schedule) if schedule else None,
        effective_access=device.effective_access,
        next_change_at=device.next_change_at,
        last_applied_access=device.last_applied_access,
        last_applied_at=device.last_applied_at,
        last_synced_at=device.last_synced_at,
        last_error=device.last_error,
        observed_blocked=device.observed_blocked,
        hostname=device.hostname,
        ip_address=device.ip_address,
        last_ssid=device.last_ssid,
        last_signal=device.last_signal,
        last_seen_at=device.last_seen_at,
        unifi_client_id=device.unifi_client_id,
        source=device.source,
        created_by=device.created_by,
        created_at=device.created_at,
        updated_at=device.updated_at,
        connected=connected,
    )


def audit_out(entry: AuditLog) -> AuditOut:
    detail = None
    if entry.detail:
        try:
            detail = json.loads(entry.detail)
        except (ValueError, TypeError):
            detail = {"raw": entry.detail}
    return AuditOut(
        id=entry.id,
        created_at=entry.created_at,
        actor=entry.actor,
        action=entry.action,
        target_mac=entry.target_mac,
        result=entry.result,
        detail=detail,
        request_id=entry.request_id,
    )
