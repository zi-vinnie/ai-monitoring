from dataclasses import dataclass

from classifier.categories import CATEGORIES, IDLE


@dataclass(frozen=True)
class CategorySummary:
    category: str
    count: int
    minutes: float


def summarize(labels: list[str], minutes_per_sample: float) -> list[CategorySummary]:
    """Turn a day's labels into estimated time-per-category.

    Each screenshot is one scheduled poll, so it stands in for roughly
    ``minutes_per_sample`` minutes of that activity (poll interval). Returns one
    entry per known category in canonical order, including zero-count ones, so
    the report shape is stable day to day. Unknown labels are ignored.
    """
    counts = {category: 0 for category in CATEGORIES}
    for label in labels:
        if label in counts:
            counts[label] += 1
    return [
        CategorySummary(category, counts[category], counts[category] * minutes_per_sample)
        for category in CATEGORIES
    ]


def total_minutes(summaries: list[CategorySummary]) -> float:
    """Minutes across every category, idle included — 'was anything recorded'."""
    return sum(summary.minutes for summary in summaries)


def active_minutes(summaries: list[CategorySummary]) -> float:
    """Minutes of active use — every category except idle.

    Idle (bare desktop / lock screen) is machine-on-but-unused time, so it's
    kept out of the headline screen-time total and the productive-share
    denominator; it still appears as its own line in the breakdown.
    """
    return sum(summary.minutes for summary in summaries if summary.category != IDLE)
