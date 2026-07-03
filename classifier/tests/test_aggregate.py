from classifier.aggregate import summarize, total_minutes
from classifier.categories import CATEGORIES


def test_summarize_counts_and_minutes():
    labels = ["gaming", "gaming", "schoolwork", "idle_locked"]
    summaries = {s.category: s for s in summarize(labels, minutes_per_sample=10)}
    assert summaries["gaming"].count == 2
    assert summaries["gaming"].minutes == 20
    assert summaries["schoolwork"].minutes == 10
    assert summaries["browsing_other"].count == 0
    assert summaries["browsing_other"].minutes == 0


def test_summarize_returns_every_category_in_order():
    summaries = summarize([], minutes_per_sample=10)
    assert [s.category for s in summaries] == list(CATEGORIES)


def test_summarize_ignores_unknown_labels():
    summaries = summarize(["gaming", "napping"], minutes_per_sample=10)
    by_cat = {s.category: s for s in summaries}
    assert by_cat["gaming"].count == 1
    assert total_minutes(summaries) == 10


def test_total_minutes_sums_all_categories():
    summaries = summarize(["gaming", "schoolwork", "social_media"], minutes_per_sample=15)
    assert total_minutes(summaries) == 45
