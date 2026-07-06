from dataclasses import dataclass
from datetime import datetime, tzinfo

MINUTES_PER_DAY = 24 * 60

# Samples are exactly `interval` apart on a healthy schedule, so same-category
# blocks that should touch land at zero gap; this only absorbs sub-minute poll
# jitter. A genuinely missed poll opens a gap wider than this, so it stays a
# gap (idle / machine off) rather than being merged over.
_MERGE_GRACE_MINUTES = 0.5


@dataclass(frozen=True)
class TimelineBlock:
    """A contiguous run of one activity, in minutes from local midnight."""

    category: str
    start_minute: float
    end_minute: float

    @property
    def duration(self) -> float:
        return self.end_minute - self.start_minute


def _minutes_from_midnight(captured_at: str, tz: tzinfo) -> float:
    """Local minute-of-day for a UTC ISO timestamp, in the report timezone."""
    local = datetime.fromisoformat(captured_at).astimezone(tz)
    return local.hour * 60 + local.minute + local.second / 60


def build_timeline(
    events: list[tuple[str, str]], tz: tzinfo, interval_minutes: float
) -> list[TimelineBlock]:
    """Turn ordered ``(captured_at, label)`` samples into day-timeline blocks.

    Each sample owns the time until the next sample, capped at one poll interval
    (so a long gap between samples shows as idle after that interval, not as a
    solid block). Consecutive samples of the same category are merged into one
    block, giving e.g. three back-to-back gaming frames as a single gaming bar.
    Everything is clamped to the ``[0, 1440)`` local day. ``events`` must be
    sorted by ``captured_at`` (as ``fetch_labeled_events`` returns them).
    """
    starts = [_minutes_from_midnight(captured_at, tz) for captured_at, _ in events]
    blocks: list[TimelineBlock] = []
    for i, ((_, label), start) in enumerate(zip(events, starts)):
        next_start = starts[i + 1] if i + 1 < len(starts) else MINUTES_PER_DAY
        end = min(start + interval_minutes, next_start, MINUTES_PER_DAY)
        if end <= start:
            continue
        last = blocks[-1] if blocks else None
        if last and last.category == label and start - last.end_minute <= _MERGE_GRACE_MINUTES:
            blocks[-1] = TimelineBlock(label, last.start_minute, max(last.end_minute, end))
        else:
            blocks.append(TimelineBlock(label, start, end))
    return blocks


def active_span(blocks: list[TimelineBlock]) -> tuple[float, float] | None:
    """First-activity to last-activity minutes-of-day, or ``None`` if empty."""
    if not blocks:
        return None
    return blocks[0].start_minute, blocks[-1].end_minute


def format_clock(minute_of_day: float) -> str:
    """A minute-of-day as a 24-hour ``HH:MM`` clock label (``1440`` -> ``24:00``)."""
    total = int(round(minute_of_day))
    hours, mins = divmod(total, 60)
    return f"{hours:02d}:{mins:02d}"
