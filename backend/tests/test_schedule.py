from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.schedule import (
    ScheduleError,
    clear_schedule,
    effective_access,
    is_active,
    load_schedule,
    next_transition,
    next_transition_for_mode,
    save_schedule,
    schedule_from_dict,
    validate_schedule,
)

UTC = timezone.utc
MONDAY = datetime(2026, 11, 16, tzinfo=UTC)
TUESDAY = datetime(2026, 11, 17, tzinfo=UTC)


def at(day: datetime, hour: int, minute: int = 0) -> datetime:
    return day.replace(hour=hour, minute=minute)


def make_schedule(kind: str = "allow_during", windows: list[dict] | None = None):
    return schedule_from_dict(
        validate_schedule(
            {
                "kind": kind,
                "timezone": "UTC",
                "windows": windows
                or [{"days": [0, 1, 2, 3, 4], "start": "09:00", "end": "17:00"}],
            }
        )
    )


def test_validation_normalizes_days_and_times():
    normalized = validate_schedule(
        {
            "kind": "allow_during",
            "timezone": "UTC",
            "windows": [{"days": [4, 0, 2, 2], "start": "9:05", "end": "17:30"}],
        }
    )
    assert normalized["windows"][0]["days"] == [0, 2, 4]
    assert normalized["windows"][0]["start"] == "09:05"
    assert normalized["windows"][0]["end"] == "17:30"


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "allow_during", "timezone": "UTC", "windows": []},
        {"kind": "nope", "timezone": "UTC", "windows": [{"days": [0], "start": "09:00", "end": "10:00"}]},
        {"kind": "allow_during", "timezone": "Mars/Base", "windows": [{"days": [0], "start": "09:00", "end": "10:00"}]},
        {"kind": "allow_during", "timezone": "UTC", "windows": [{"days": [], "start": "09:00", "end": "10:00"}]},
        {"kind": "allow_during", "timezone": "UTC", "windows": [{"days": [7], "start": "09:00", "end": "10:00"}]},
        {"kind": "allow_during", "timezone": "UTC", "windows": [{"days": [0], "start": "09:00", "end": "09:00"}]},
        {"kind": "allow_during", "timezone": "UTC", "windows": [{"days": [0], "start": "9am", "end": "10:00"}]},
    ],
)
def test_validation_rejects_bad_payloads(payload):
    with pytest.raises(ScheduleError):
        validate_schedule(payload)


def test_weekday_window_is_end_exclusive():
    schedule = make_schedule()
    assert is_active(schedule, at(MONDAY, 9, 0))
    assert is_active(schedule, at(MONDAY, 16, 59))
    assert not is_active(schedule, at(MONDAY, 8, 59))
    assert not is_active(schedule, at(MONDAY, 17, 0))
    assert not is_active(schedule, datetime(2026, 11, 15, 12, tzinfo=UTC))  # Sunday


def test_overnight_window_checks_previous_day():
    schedule = make_schedule(
        windows=[{"days": [0], "start": "22:00", "end": "07:00"}]
    )
    assert not is_active(schedule, at(MONDAY, 21, 59))
    assert is_active(schedule, at(MONDAY, 23, 0))
    assert is_active(schedule, at(TUESDAY, 6, 30))
    assert not is_active(schedule, at(TUESDAY, 7, 0))
    assert not is_active(schedule, at(TUESDAY, 23, 0))


def test_block_during_is_inverse():
    schedule = make_schedule(
        kind="block_during",
        windows=[{"days": [5, 6], "start": "00:00", "end": "23:59"}],
    )
    saturday = datetime(2026, 11, 21, 12, tzinfo=UTC)
    assert effective_access("scheduled", schedule, saturday) == "blocked"
    assert effective_access("scheduled", schedule, at(MONDAY, 12)) == "allowed"


def test_direct_modes_ignore_schedule():
    schedule = make_schedule()
    assert effective_access("allowed", schedule, at(MONDAY, 3)) == "allowed"
    assert effective_access("blocked", schedule, at(MONDAY, 12)) == "blocked"
    assert effective_access("ignored", schedule, at(MONDAY, 12)) == "ignored"


def test_invalid_schedule_fails_closed():
    assert effective_access("scheduled", None, at(MONDAY, 12)) == "blocked"


def test_next_transition():
    schedule = make_schedule()
    assert next_transition(schedule, at(MONDAY, 8, 0)) == at(MONDAY, 9, 0)
    assert next_transition(schedule, at(MONDAY, 10, 0)) == at(MONDAY, 17, 0)
    friday_evening = datetime(2026, 11, 20, 18, tzinfo=UTC)
    assert next_transition(schedule, friday_evening) == datetime(2026, 11, 23, 9, tzinfo=UTC)
    assert next_transition_for_mode("allowed", schedule, at(MONDAY, 10)) is None


def test_timezone_conversion():
    schedule = schedule_from_dict(
        validate_schedule(
            {
                "kind": "allow_during",
                "timezone": "America/New_York",
                "windows": [{"days": [0], "start": "09:00", "end": "17:00"}],
            }
        )
    )
    # November 16 2026 is EST (UTC-5): 09:00 local == 14:00 UTC.
    assert is_active(schedule, datetime(2026, 11, 16, 14, 0, tzinfo=UTC))
    assert not is_active(schedule, datetime(2026, 11, 16, 13, 59, tzinfo=UTC))


def test_save_load_clear_round_trip():
    device = SimpleNamespace()
    normalized = validate_schedule(
        {
            "kind": "block_during",
            "timezone": "Europe/London",
            "windows": [{"days": [1, 3], "start": "18:00", "end": "22:30"}],
        }
    )
    save_schedule(device, normalized)
    loaded = load_schedule(device)
    assert loaded is not None
    assert loaded.kind == "block_during"
    assert loaded.timezone == "Europe/London"
    assert loaded.windows[0].days == (1, 3)
    clear_schedule(device)
    assert load_schedule(device) is None
