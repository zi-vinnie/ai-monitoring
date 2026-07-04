from datetime import date, datetime, timedelta

from zoneinfo import ZoneInfo

from classifier.timeframe import day_bounds_utc, parse_date


def test_parse_explicit_date():
    tz = ZoneInfo("UTC")
    assert parse_date("2026-07-02", tz) == date(2026, 7, 2)


def test_parse_date_yesterday_keyword():
    tz = ZoneInfo("UTC")
    expected = datetime.now(tz).date() - timedelta(days=1)
    assert parse_date("yesterday", tz) == expected
    assert parse_date("  Yesterday ", tz) == expected


def test_parse_date_today_keyword_matches_default():
    tz = ZoneInfo("UTC")
    assert parse_date("today", tz) == parse_date(None, tz)


def test_day_bounds_utc_for_utc_zone():
    start, end = day_bounds_utc(date(2026, 7, 2), ZoneInfo("UTC"))
    assert start == "2026-07-02T00:00:00+00:00"
    assert end == "2026-07-03T00:00:00+00:00"


def test_day_bounds_utc_shifts_for_positive_offset():
    # A local day in a +02:00 summer zone starts two hours earlier in UTC and
    # the window is still exactly 24h wide.
    start, end = day_bounds_utc(date(2026, 7, 2), ZoneInfo("Europe/Berlin"))
    assert start == "2026-07-01T22:00:00+00:00"
    assert end == "2026-07-02T22:00:00+00:00"


def test_day_bounds_utc_shifts_for_negative_offset():
    start, end = day_bounds_utc(date(2026, 7, 2), ZoneInfo("America/New_York"))
    assert start == "2026-07-02T04:00:00+00:00"
    assert end == "2026-07-03T04:00:00+00:00"
