from datetime import date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo


def resolve_tz(name: str | None) -> tzinfo:
    """The timezone that defines a report/classify "day".

    A named IANA zone (e.g. ``Europe/London``) when ``REPORT_TZ`` is set,
    otherwise the server's local zone. Screenshots are timestamped in UTC, but
    "yesterday" only makes sense in a local calendar.
    """
    if name:
        return ZoneInfo(name)
    return datetime.now().astimezone().tzinfo or timezone.utc


def parse_date(value: str | None, tz: tzinfo) -> date:
    """Target day: an explicit ``YYYY-MM-DD``, else today in ``tz``."""
    if value:
        return date.fromisoformat(value)
    return datetime.now(tz).date()


def day_bounds_utc(day: date, tz: tzinfo) -> tuple[str, str]:
    """UTC ISO bounds ``[start, end)`` spanning the local calendar ``day``.

    ``captured_at`` is stored as a UTC ISO-8601 string, so a local day maps to a
    half-open UTC interval. Returned as ISO strings so callers can compare
    directly in SQL (all stored timestamps share the ``+00:00`` offset, so the
    comparison is a well-ordered string comparison).
    """
    start_local = datetime.combine(day, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return (
        start_local.astimezone(timezone.utc).isoformat(),
        end_local.astimezone(timezone.utc).isoformat(),
    )
