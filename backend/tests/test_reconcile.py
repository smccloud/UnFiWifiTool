from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401  (register tables)
from app.db import Base
from app.models import AuditLog, Device
from app.reconcile import apply_device_now, sync
from app.schedule import save_schedule, validate_schedule
from app.unifi.errors import UniFiCapabilityError
from app.unifi.types import LiveClient

MAC = "aa:bb:cc:dd:ee:ff"
NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)  # Monday


class FakeService:
    def __init__(self, clients: list[LiveClient] | None = None, fail: bool = False):
        self.clients = clients or []
        self.fail = fail
        self.calls: list[tuple[str, bool]] = []

    def list_clients(self) -> list[LiveClient]:
        return self.clients

    def set_blocked(self, mac: str, blocked: bool) -> None:
        if self.fail:
            raise UniFiCapabilityError("block/unblock needs local admin credentials")
        self.calls.append((mac, blocked))


def settings(**overrides):
    values = {"discovery_enabled": True, "auto_apply": True, "dry_run": False}
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def add_device(db, mode: str = "blocked", **kwargs) -> Device:
    device = Device(mac=MAC, access_mode=mode, source="manual", **kwargs)
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def test_sync_blocks_a_connected_unblocked_device(db, monkeypatch):
    monkeypatch.setattr("app.reconcile.utcnow", lambda: NOW)
    device = add_device(db)
    service = FakeService([LiveClient(mac=MAC, blocked=False)])

    summary = sync(db, service, settings(), actor="tester")

    assert service.calls == [(MAC, True)]
    assert summary.applied == 1
    db.refresh(device)
    assert device.last_applied_access == "blocked"
    assert device.observed_blocked is False
    assert device.last_error is None
    actions = [entry.action for entry in db.query(AuditLog).all()]
    assert "block" in actions


def test_sync_does_nothing_when_already_blocked(db, monkeypatch):
    monkeypatch.setattr("app.reconcile.utcnow", lambda: NOW)
    add_device(db, last_applied_access="blocked")
    service = FakeService([LiveClient(mac=MAC, blocked=True)])

    summary = sync(db, service, settings(), actor="tester")

    assert service.calls == []
    assert summary.skipped == 1


def test_sync_unblocks_drift(db, monkeypatch):
    monkeypatch.setattr("app.reconcile.utcnow", lambda: NOW)
    device = add_device(db, mode="allowed", last_applied_access="blocked")
    service = FakeService([LiveClient(mac=MAC, blocked=True)])

    sync(db, service, settings(), actor="tester")

    assert service.calls == [(MAC, False)]
    db.refresh(device)
    assert device.last_applied_access == "allowed"


def test_sync_does_not_unblock_a_device_that_was_never_blocked(db, monkeypatch):
    monkeypatch.setattr("app.reconcile.utcnow", lambda: NOW)
    add_device(db, mode="allowed")
    service = FakeService([LiveClient(mac=MAC, blocked=False)])

    sync(db, service, settings(), actor="tester")

    assert service.calls == []


def scheduled_device(db, start: str, end: str, last_applied: str | None = None):
    device = add_device(db, mode="scheduled", last_applied_access=last_applied)
    normalized = validate_schedule(
        {
            "kind": "allow_during",
            "timezone": "UTC",
            "windows": [{"days": [0, 1, 2, 3, 4], "start": start, "end": end}],
        }
    )
    save_schedule(device, normalized)
    db.commit()
    db.refresh(device)
    return device


def test_schedule_blocks_outside_window(db, monkeypatch):
    monkeypatch.setattr("app.reconcile.utcnow", lambda: NOW)
    device = scheduled_device(db, "09:00", "10:00")
    service = FakeService([LiveClient(mac=MAC, blocked=False)])

    summary = sync(db, service, settings(), actor="tester")

    assert service.calls == [(MAC, True)]
    assert summary.applied == 1
    db.refresh(device)
    assert device.effective_access == "blocked"
    assert device.next_change_at is not None
    assert device.next_change_at.date().isoformat() == "2026-11-17"


def test_schedule_unblocks_inside_window(db, monkeypatch):
    monkeypatch.setattr("app.reconcile.utcnow", lambda: NOW)
    device = scheduled_device(db, "09:00", "17:00", last_applied="blocked")
    service = FakeService([LiveClient(mac=MAC, blocked=True)])

    sync(db, service, settings(), actor="tester")

    assert service.calls == [(MAC, False)]
    db.refresh(device)
    assert device.effective_access == "allowed"
    assert device.last_applied_access == "allowed"


def test_dry_run_never_calls_controller(db, monkeypatch):
    monkeypatch.setattr("app.reconcile.utcnow", lambda: NOW)
    device = add_device(db)
    service = FakeService([LiveClient(mac=MAC, blocked=False)])

    summary = sync(db, service, settings(dry_run=True), actor="tester")

    assert service.calls == []
    assert summary.dry_run is True
    assert summary.transitions and summary.transitions[0]["dryRun"] is True
    db.refresh(device)
    assert device.last_applied_access is None
    assert any(entry.action == "dry_run" for entry in db.query(AuditLog).all())


def test_auto_apply_off_does_not_call_controller(db, monkeypatch):
    monkeypatch.setattr("app.reconcile.utcnow", lambda: NOW)
    add_device(db)
    service = FakeService([LiveClient(mac=MAC, blocked=False)])

    sync(db, service, settings(auto_apply=False), actor="tester")

    assert service.calls == []


def test_discovery_creates_unmanaged_device(db, monkeypatch):
    monkeypatch.setattr("app.reconcile.utcnow", lambda: NOW)
    service = FakeService([LiveClient(mac=MAC, name="New phone", blocked=False)])

    summary = sync(db, service, settings(), actor="tester")

    assert summary.discovered == 1
    device = db.query(Device).filter(Device.mac == MAC).one()
    assert device.source == "discovered"
    assert device.access_mode == "ignored"
    assert device.hostname == "New phone"
    assert service.calls == []


def test_discovery_ignores_wired_clients(db, monkeypatch):
    monkeypatch.setattr("app.reconcile.utcnow", lambda: NOW)
    service = FakeService(
        [LiveClient(mac=MAC, name="Office PC", connection_type="wired")]
    )

    summary = sync(db, service, settings(), actor="tester")

    assert summary.discovered == 0
    assert db.query(Device).count() == 0


def test_existing_device_seen_as_wired_is_not_enforced(db, monkeypatch):
    monkeypatch.setattr("app.reconcile.utcnow", lambda: NOW)
    device = add_device(db, mode="blocked")
    service = FakeService(
        [LiveClient(mac=MAC, blocked=False, connection_type="wired")]
    )

    summary = sync(db, service, settings(), actor="tester")

    assert service.calls == []
    assert summary.applied == 0
    db.refresh(device)
    assert device.connection_type == "wired"


def test_discovery_can_be_disabled(db, monkeypatch):
    monkeypatch.setattr("app.reconcile.utcnow", lambda: NOW)
    service = FakeService([LiveClient(mac=MAC, blocked=False)])

    sync(db, service, settings(discovery_enabled=False), actor="tester")

    assert db.query(Device).count() == 0


def test_apply_device_now_reports_capability_failure(db):
    device = add_device(db)
    service = FakeService(fail=True)

    ok, error = apply_device_now(
        db, service, settings(), device, actor="tester", reason="test"
    )

    assert ok is False
    assert error and "local admin" in error
    db.commit()
    db.refresh(device)
    assert device.last_error and "local admin" in device.last_error
    entry = db.query(AuditLog).filter(AuditLog.action == "block").one()
    assert entry.result == "failure"


def test_sync_records_last_sync(db, monkeypatch):
    monkeypatch.setattr("app.reconcile.utcnow", lambda: NOW)
    service = FakeService([])

    sync(db, service, settings(), actor="tester")

    from app.runtime import get_setting

    last_sync = get_setting(db, "last_sync")
    assert isinstance(last_sync, dict)
    assert last_sync["dry_run"] is False
