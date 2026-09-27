"""Time helpers. Everything is stored in UTC ISO-8601; local time is only for scheduling and display."""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

UTC = dt.UTC

_frozen: dt.datetime | None = None


def now() -> dt.datetime:
    """Current UTC time. Tests can freeze it with `freeze()`."""
    return _frozen if _frozen is not None else dt.datetime.now(UTC)


def freeze(t: dt.datetime | str | None) -> None:
    global _frozen
    _frozen = parse(t) if isinstance(t, str) else t


def iso(t: dt.datetime | None) -> str | None:
    if t is None:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return t.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def now_iso() -> str:
    return iso(now())  # type: ignore[return-value]


def parse(s: str | dt.datetime | None) -> dt.datetime | None:
    """Parse ISO strings (with Z, offsets, or naive = UTC) and plain dates."""
    if s is None or s == "":
        return None
    if isinstance(s, dt.datetime):
        return s if s.tzinfo else s.replace(tzinfo=UTC)
    text = s.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        t = dt.datetime.fromisoformat(text)
    except ValueError:
        try:
            d = dt.date.fromisoformat(text[:10])
        except ValueError:
            return None
        t = dt.datetime(d.year, d.month, d.day)
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return t.astimezone(UTC)


def local(t: dt.datetime, tz: str) -> dt.datetime:
    return t.astimezone(ZoneInfo(tz))


def local_date(t: dt.datetime, tz: str) -> dt.date:
    return local(t, tz).date()


def local_hhmm(t: dt.datetime, tz: str) -> str:
    return local(t, tz).strftime("%H:%M")


def iso_week(d: dt.date) -> str:
    year, week, _ = d.isocalendar()
    return f"{year}-W{week:02d}"


def hours_between(a: dt.datetime | None, b: dt.datetime | None) -> float | None:
    if a is None or b is None:
        return None
    return (b - a).total_seconds() / 3600.0


def age_hours(t: dt.datetime | str | None, ref: dt.datetime | None = None) -> float | None:
    tt = parse(t) if not isinstance(t, dt.datetime) else t
    if tt is None:
        return None
    return max(0.0, ((ref or now()) - tt).total_seconds() / 3600.0)


def local_midnight_utc(d: dt.date, tz: str) -> dt.datetime:
    """UTC instant of local midnight at the start of local date `d`."""
    return dt.datetime(d.year, d.month, d.day, tzinfo=ZoneInfo(tz)).astimezone(UTC)


def at_local_time(d: dt.date, hhmm: str, tz: str) -> dt.datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return dt.datetime(d.year, d.month, d.day, h, m, tzinfo=ZoneInfo(tz)).astimezone(UTC)


def month_key(value: str | dt.datetime | None) -> str:
    t = parse(value) if not isinstance(value, dt.datetime) else value
    if t is None:
        return "undated"
    return t.strftime("%Y-%m")
