from classifier.aggregate import active_minutes, summarize, total_minutes
from classifier.categories import CATEGORIES


def test_summarize_counts_and_minutes():
    labels = ["gaming", "gaming", "productive", "idle"]
    summaries = {s.category: s for s in summarize(labels, minutes_per_sample=10)}
    assert summaries["gaming"].count == 2
    assert summaries["gaming"].minutes == 20
    assert summaries["productive"].minutes == 10
    assert summaries["idle"].minutes == 10
    assert summaries["browsing"].count == 0
    assert summaries["browsing"].minutes == 0


def test_summarize_returns_every_category_in_order():
    summaries = summarize([], minutes_per_sample=10)
    assert [s.category for s in summaries] == list(CATEGORIES)


def test_summarize_ignores_unrecognized_labels():
    summaries = summarize(["gaming", "napping"], minutes_per_sample=10)
    by_cat = {s.category: s for s in summaries}
    assert by_cat["gaming"].count == 1
    assert total_minutes(summaries) == 10


def test_total_minutes_sums_all_categories():
    summaries = summarize(["gaming", "productive", "social_media"], minutes_per_sample=15)
    assert total_minutes(summaries) == 45


def test_active_minutes_excludes_idle():
    summaries = summarize(["productive", "gaming", "idle", "idle"], minutes_per_sample=10)
    assert total_minutes(summaries) == 40
    assert active_minutes(summaries) == 20
