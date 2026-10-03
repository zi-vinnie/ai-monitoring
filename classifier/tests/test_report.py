from datetime import date

from classifier.aggregate import summarize
from classifier.report import DayData, _merge_summaries, build_range_text_body


def _day(day: date, labels: list[str]) -> DayData:
    return DayData(day, summarize(labels, 10), [], [])


def test_merge_summaries_adds_across_days():
    days = [_day(date(2026, 9, 28), ["gaming", "gaming"]), _day(date(2026, 9, 29), ["gaming", "productive"])]
    merged = {s.category: s for s in _merge_summaries(days)}
    assert merged["gaming"].minutes == 30
    assert merged["productive"].minutes == 10


def test_range_text_marks_days_without_data_and_averages_over_days_with_data():
    days = [_day(date(2026, 9, 28), ["gaming"] * 6), _day(date(2026, 9, 29), [])]
    text = build_range_text_body(days, "Mon 28 Sep – Tue 29 Sep 2026")
    assert "no data (PC off or offline)" in text
    assert "Daily average:      1h (over 1 day(s) with data)" in text
    assert "mostly Gaming" in text
