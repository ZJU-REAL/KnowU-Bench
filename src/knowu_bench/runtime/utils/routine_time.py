from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import Any, Mapping

from loguru import logger


_WEEKDAYS = {
    "mon": 0,
    "monday": 0,
    "tue": 1,
    "tues": 1,
    "tuesday": 1,
    "wed": 2,
    "wednesday": 2,
    "thu": 3,
    "thur": 3,
    "thurs": 3,
    "thursday": 3,
    "fri": 4,
    "friday": 4,
    "sat": 5,
    "saturday": 5,
    "sun": 6,
    "sunday": 6,
}


def format_adb_datetime(dt: datetime) -> str:
    """Format a datetime for Android's `date MMDDhhmmYYYY.ss` command."""
    return dt.strftime("%m%d%H%M%Y.%S")


def resolve_routine_datetime(
    trigger: Mapping[str, Any] | None = None,
    *,
    default_time: str | datetime | time,
    now: datetime | None = None,
    task_name: str = "routine",
) -> datetime:
    """
    Resolve a routine simulation datetime from profile trigger fields.

    `simulation_datetime` is treated as a time-of-day hint only. The final date
    comes from the current local date, adjusted to the nearest configured weekday
    when `day_of_week` or `days` is present.
    """
    trigger = trigger or {}
    base_now = now or datetime.now()
    weekdays = _parse_weekdays(trigger.get("day_of_week") or trigger.get("days"))

    sim_raw = trigger.get("simulation_datetime") or trigger.get("datetime")
    sim_dt = _parse_datetime_like(sim_raw)
    sim_time = sim_dt.time().replace(microsecond=0) if sim_dt else _parse_time_like(sim_raw)
    if sim_dt and weekdays and sim_dt.weekday() not in weekdays:
        logger.warning(
            f"{task_name}: ignoring date from simulation_datetime={sim_dt:%Y-%m-%d %H:%M:%S} "
            f"because it conflicts with configured weekday(s)."
        )

    resolved_time = (
        sim_time
        or _parse_time_like(trigger.get("time"))
        or _parse_time_range_start(trigger.get("time_range"))
        or _parse_time_like(default_time)
    )
    if resolved_time is None:
        logger.warning(f"{task_name}: invalid routine time config; falling back to 00:00.")
        resolved_time = time(0, 0, 0)

    resolved_date = _nearest_weekday(base_now.date(), weekdays) if weekdays else base_now.date()
    return datetime.combine(resolved_date, resolved_time)


def _nearest_weekday(base_date: date, weekdays: set[int]) -> date:
    for offset in range(7):
        candidate = base_date + timedelta(days=offset)
        if candidate.weekday() in weekdays:
            return candidate
    return base_date


def _parse_weekdays(raw: Any) -> set[int]:
    if raw is None:
        return set()
    values = raw if isinstance(raw, (list, tuple, set)) else [raw]
    weekdays: set[int] = set()
    for value in values:
        key = str(value).strip().lower()
        if key in _WEEKDAYS:
            weekdays.add(_WEEKDAYS[key])
    return weekdays


def _parse_time_range_start(raw: Any) -> time | None:
    if not isinstance(raw, (list, tuple)) or not raw:
        return None
    return _parse_time_like(raw[0])


def _parse_datetime_like(raw: Any) -> datetime | None:
    if isinstance(raw, datetime):
        return raw.replace(microsecond=0)
    if isinstance(raw, time):
        return None
    text = str(raw or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m%d%H%M%Y.%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _parse_time_like(raw: Any) -> time | None:
    if isinstance(raw, datetime):
        return raw.time().replace(microsecond=0)
    if isinstance(raw, time):
        return raw.replace(microsecond=0)
    text = str(raw or "").strip()
    if not text:
        return None

    parsed_dt = _parse_datetime_like(text)
    if parsed_dt:
        return parsed_dt.time().replace(microsecond=0)

    match = re.search(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b", text)
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    second = int(match.group(3) or 0)
    if hour > 23 or minute > 59 or second > 59:
        return None
    return time(hour, minute, second)
