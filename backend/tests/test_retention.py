from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401  (register tables)
from app.db import Base
from app.models import AuditLog
from app.retention import (
    LAST_PURGE_SETTING,
    RETENTION_SETTING,
    get_retention_days,
    purge_if_due,
    purge_old_audit,
    set_retention_days,
)
from app.runtime import get_setting, set_setting
from app.timeutil import utcnow


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


def add_entry(db, days_ago: int, action: str = "login") -> AuditLog:
    entry = AuditLog(
        created_at=utcnow() - timedelta(days=days_ago),
        actor="tester",
        action=action,
        result="success",
    )
    db.add(entry)
    db.commit()
    return entry


def test_purge_removes_only_old_entries(db):
    add_entry(db, days_ago=40, action="block")
    add_entry(db, days_ago=5, action="login")

    result = purge_old_audit(db, 30, actor="tester")

    assert result.deleted == 1
    assert result.retention_days == 30
    assert result.ran is True
    actions = [entry.action for entry in db.query(AuditLog).all()]
    assert "block" not in actions
    assert "login" in actions
    assert "audit_purged" in actions
    last = get_setting(db, LAST_PURGE_SETTING)
    assert last["deleted"] == 1
    assert last["retentionDays"] == 30


def test_zero_retention_keeps_everything(db):
    add_entry(db, days_ago=500)

    result = purge_old_audit(db, 0, actor="tester")

    assert result.deleted == 0
    assert result.ran is False
    assert db.query(AuditLog).count() == 1
    assert get_setting(db, LAST_PURGE_SETTING) is None


def test_runtime_retention_override(db):
    set_retention_days(db, 7)
    db.commit()
    assert get_retention_days(db) == 7
    assert get_setting(db, RETENTION_SETTING) == 7

    with pytest.raises(ValueError):
        set_retention_days(db, -1)
    with pytest.raises(ValueError):
        set_retention_days(db, 36_501)


def test_purge_if_due_waits_a_day(db):
    add_entry(db, days_ago=40, action="block")
    set_retention_days(db, 30)
    set_setting(db, LAST_PURGE_SETTING, {"at": utcnow().isoformat(), "deleted": 0})
    db.commit()

    assert purge_if_due(db) is None
    assert db.query(AuditLog).filter(AuditLog.action == "block").count() == 1

    set_setting(
        db,
        LAST_PURGE_SETTING,
        {"at": (utcnow() - timedelta(hours=25)).isoformat(), "deleted": 0},
    )
    db.commit()

    result = purge_if_due(db)
    assert result is not None
    assert result.deleted == 1
    assert db.query(AuditLog).filter(AuditLog.action == "block").count() == 0


def test_purge_if_due_disabled_when_retention_is_zero(db):
    add_entry(db, days_ago=500)
    set_retention_days(db, 0)
    db.commit()

    assert purge_if_due(db) is None
    assert db.query(AuditLog).count() == 1
