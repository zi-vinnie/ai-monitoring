from zoneinfo import ZoneInfo

from classifier.timeline import (
    MINUTES_PER_DAY,
    active_span,
    build_timeline,
    format_clock,
)

UTC = ZoneInfo("UTC")


def _events(*pairs: tuple[str, str]) -> list[tuple[str, str]]:
    """(HH:MM UTC, label) shorthand -> (iso, label) on 2026-07-05."""
    return [(f"2026-07-05T{hhmm}:00+00:00", label) for hhmm, label in pairs]


def test_consecutive_same_category_merge_into_one_block():
    events = _events(("09:00", "gaming"), ("09:10", "gaming"), ("09:20", "gaming"))
    blocks = build_timeline(events, UTC, interval_minutes=10)
    assert len(blocks) == 1
    assert blocks[0].category == "gaming"
    assert (blocks[0].start_minute, blocks[0].end_minute) == (9 * 60, 9 * 60 + 30)


def test_different_categories_abut_without_gap():
    events = _events(("09:00", "gaming"), ("09:10", "productive"))
    blocks = build_timeline(events, UTC, interval_minutes=10)
    assert [b.category for b in blocks] == ["gaming", "productive"]
    # First block is capped at the next sample, so the two touch exactly.
    assert blocks[0].end_minute == blocks[1].start_minute == 9 * 60 + 10


def test_missed_poll_leaves_an_idle_gap():
    # Same category resumes 30m later; the block only owns one interval, so the
    # 20m absence stays a gap rather than merging.
    events = _events(("09:00", "gaming"), ("09:30", "gaming"))
    blocks = build_timeline(events, UTC, interval_minutes=10)
    assert len(blocks) == 2
    assert blocks[0].end_minute == 9 * 60 + 10
    assert blocks[1].start_minute == 9 * 60 + 30


def test_timezone_converts_to_local_minute_of_day():
    events = _events(("23:30", "productive"))  # 00:30 next day in London (BST +1)
    blocks = build_timeline(events, ZoneInfo("Europe/London"), interval_minutes=10)
    assert blocks[0].start_minute == 30


def test_last_block_clamps_to_end_of_day():
    events = _events(("23:55", "browsing"))
    blocks = build_timeline(events, UTC, interval_minutes=10)
    assert blocks[0].end_minute == MINUTES_PER_DAY


def test_empty_events_produce_no_blocks_or_span():
    assert build_timeline([], UTC, interval_minutes=10) == []
    assert active_span([]) is None


def test_active_span_spans_first_to_last():
    events = _events(("08:00", "productive"), ("22:00", "gaming"))
    span = active_span(build_timeline(events, UTC, interval_minutes=10))
    assert span == (8 * 60, 22 * 60 + 10)


def test_format_clock():
    assert format_clock(0) == "00:00"
    assert format_clock(9 * 60 + 5) == "09:05"
    assert format_clock(MINUTES_PER_DAY) == "24:00"
