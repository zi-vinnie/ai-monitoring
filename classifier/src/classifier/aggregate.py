from dataclasses import dataclass

from classifier.categories import CATEGORIES


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
    return sum(summary.minutes for summary in summaries)
