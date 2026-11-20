from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
VALID_KINDS = {"allow_during", "block_during"}
VALID_MODES = {"allowed", "blocked", "scheduled", "ignored"}
DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MAX_WINDOWS = 24


class ScheduleError(ValueError):
    pass


@dataclass(frozen=True)
class ScheduleWindow:
    days: tuple[int, ...]
    start: time
    end: time

    @property
    def crosses_midnight(self) -> bool:
        return self.end <= self.start


@dataclass(frozen=True)
class Schedule:
    kind: str
    timezone: str
    windows: tuple[ScheduleWindow, ...]

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


def _parse_clock(value: str, field: str) -> time:
    if not isinstance(value, str) or not TIME_RE.match(value.strip()):
        raise ScheduleError(f"{field} must be a 24-hour time like 08:30")
    hour, minute = value.strip().split(":")
    return time(int(hour), int(minute))


def validate_schedule(payload: dict) -> dict:
    """Validate a schedule payload and return a normalized dict."""
    if not isinstance(payload, dict):
        raise ScheduleError("schedule must be an object")

    kind = payload.get("kind", "allow_during")
    if kind not in VALID_KINDS:
        raise ScheduleError("schedule.kind must be allow_during or block_during")

    tz_name = payload.get("timezone") or "UTC"
    if not isinstance(tz_name, str):
        raise ScheduleError("schedule.timezone must be a string")
    try:
        ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ScheduleError(f"Unknown timezone: {tz_name}") from exc

    raw_windows = payload.get("windows")
    if not isinstance(raw_windows, list) or not raw_windows:
        raise ScheduleError("schedule.windows must contain at least one window")
    if len(raw_windows) > MAX_WINDOWS:
        raise ScheduleError(f"at most {MAX_WINDOWS} windows are allowed")

    normalized_windows: list[dict] = []
    for index, raw in enumerate(raw_windows, start=1):
        if not isinstance(raw, dict):
            raise ScheduleError(f"window {index} must be an object")
        days = raw.get("days")
        if not isinstance(days, list) or not days:
            raise ScheduleError(f"window {index} must select at least one day")
        clean_days: set[int] = set()
        for day in days:
            if not isinstance(day, int) or isinstance(day, bool) or day < 0 or day > 6:
                raise ScheduleError(f"window {index}: days must be integers 0-6 (Mon-Sun)")
            clean_days.add(day)
        start = _parse_clock(raw.get("start"), f"window {index} start")
        end = _parse_clock(raw.get("end"), f"window {index} end")
        if start == end:
            raise ScheduleError(f"window {index}: start and end must differ")
        normalized_windows.append(
            {
                "days": sorted(clean_days),
                "start": start.strftime("%H:%M"),
                "end": end.strftime("%H:%M"),
            }
        )

    normalized_windows.sort(key=lambda item: (item["start"], item["end"]))
    return {"kind": kind, "timezone": tz_name, "windows": normalized_windows}


def schedule_from_dict(payload: dict) -> Schedule:
    normalized = payload if "windows" in payload else validate_schedule(payload)
    return Schedule(
        kind=normalized["kind"],
        timezone=normalized["timezone"],
        windows=tuple(
            ScheduleWindow(
                days=tuple(window["days"]),
                start=_parse_clock(window["start"], "start"),
                end=_parse_clock(window["end"], "end"),
            )
            for window in normalized["windows"]
        ),
    )


def load_schedule(device) -> Schedule | None:  # noqa: ANN001
    if not device.schedule_windows or not device.schedule_timezone:
        return None
    try:
        windows = json.loads(device.schedule_windows)
        return schedule_from_dict(
            {
                "kind": device.schedule_kind,
                "timezone": device.schedule_timezone,
                "windows": windows,
            }
        )
    except (ValueError, TypeError, KeyError, ScheduleError):
        return None


def save_schedule(device, normalized: dict) -> None:  # noqa: ANN001
    device.schedule_kind = normalized["kind"]
    device.schedule_timezone = normalized["timezone"]
    device.schedule_windows = json.dumps(normalized["windows"], separators=(",", ":"))


def clear_schedule(device) -> None:  # noqa: ANN001
    device.schedule_kind = "allow_during"
    device.schedule_timezone = None
    device.schedule_windows = None
    device.next_change_at = None


def schedule_to_dict(schedule: Schedule | None) -> dict | None:
    if schedule is None:
        return None
    return {
        "kind": schedule.kind,
        "timezone": schedule.timezone,
        "windows": [
            {
                "days": list(window.days),
                "start": window.start.strftime("%H:%M"),
                "end": window.end.strftime("%H:%M"),
            }
            for window in schedule.windows
        ],
    }


def _localize(value: datetime, tz: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(tz)


def _window_bounds(day: date, window: ScheduleWindow, tz: ZoneInfo) -> tuple[datetime, datetime]:
    start = datetime.combine(day, window.start, tzinfo=tz)
    end_day = day + timedelta(days=1) if window.crosses_midnight else day
    end = datetime.combine(end_day, window.end, tzinfo=tz)
    return start, end


def is_active(schedule: Schedule, at: datetime) -> bool:
    """Return True when `at` falls inside any schedule window."""
    local = _localize(at, schedule.tz)
    today = local.date()
    # Check today and yesterday so windows that cross midnight are covered.
    for offset in (0, -1):
        day = today + timedelta(days=offset)
        for window in schedule.windows:
            if day.weekday() not in window.days:
                continue
            start, end = _window_bounds(day, window, schedule.tz)
            if start <= local < end:
                return True
    return False


def effective_access(access_mode: str, schedule: Schedule | None, at: datetime) -> str:
    """Compute the access state that should be enforced at `at`."""
    if access_mode not in VALID_MODES:
        raise ScheduleError(f"Unknown access mode: {access_mode}")
    if access_mode == "ignored":
        return "ignored"
    if access_mode == "allowed":
        return "allowed"
    if access_mode == "blocked":
        return "blocked"
    if schedule is None:
        # Fail closed if the stored schedule is unreadable.
        return "blocked"
    active = is_active(schedule, at)
    if schedule.kind == "allow_during":
        return "allowed" if active else "blocked"
    return "blocked" if active else "allowed"


def next_transition(schedule: Schedule, at: datetime) -> datetime | None:
    """Find the next instant at which the schedule's active state changes."""
    local = _localize(at, schedule.tz)
    current = is_active(schedule, at)
    today = local.date()
    candidates: list[datetime] = []

    for offset in range(0, 9):
        day = today + timedelta(days=offset)
        for window in schedule.windows:
            if day.weekday() not in window.days:
                continue
            start, end = _window_bounds(day, window, schedule.tz)
            for boundary in (start, end):
                if boundary <= local:
                    continue
                if is_active(schedule, boundary.astimezone(timezone.utc)) != current:
                    candidates.append(boundary)

    if not candidates:
        return None
    return min(candidates).astimezone(timezone.utc)


def next_transition_for_mode(access_mode: str, schedule: Schedule | None, at: datetime) -> datetime | None:
    if access_mode != "scheduled" or schedule is None:
        return None
    return next_transition(schedule, at)
