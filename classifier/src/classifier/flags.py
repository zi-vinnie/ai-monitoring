import re
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo

from classifier.categories import STRANGER_CHAT_SITE, VIDEO_PAGE

# Activities a parent should see called out by name in the report, not just
# folded into a category total. Each flag is a reason shown in the email plus
# window-title patterns (searched case-insensitively). Video pages are skipped
# so a YouTube video *about* one of these sites doesn't trip the flag.
_FLAGS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "Random video chat with strangers (Omegle, OmeTV, Monkey and similar)",
        re.compile(
            STRANGER_CHAT_SITE + r"|random (cam|video) chat|talk to strangers",
            re.IGNORECASE,
        ),
    ),
)


def flag_for_title(window_title: str | None) -> str | None:
    """The flag reason a window title trips, or None."""
    if not window_title or VIDEO_PAGE.search(window_title):
        return None
    for reason, pattern in _FLAGS:
        if pattern.search(window_title):
            return reason
    return None


# Matches this many polls apart still count as one session (a quick switch to
# another tab, or a single missed poll, doesn't split it).
_SESSION_GAP_POLLS = 3


@dataclass(frozen=True)
class FlagSummary:
    """Estimated time on one flagged activity, and when it was seen (local).

    ``sessions`` are ``(first, last)`` sample times of each separate stretch,
    so two visits hours apart don't read as one long session.
    """

    reason: str
    count: int
    minutes: float
    sessions: tuple[tuple[datetime, datetime], ...]

    @property
    def first_seen(self) -> datetime:
        return self.sessions[0][0]


def summarize_flags(
    samples: list[tuple[str, str | None]], tz: tzinfo, minutes_per_sample: float
) -> list[FlagSummary]:
    """Group ordered ``(captured_at, window_title)`` samples by flag reason.

    Like the category totals, each matching screenshot stands in for one poll
    interval. Matches more than a few polls apart start a new session. Reasons
    are returned in the order they were first seen.
    """
    session_gap = timedelta(minutes=_SESSION_GAP_POLLS * minutes_per_sample)
    seen: dict[str, list[datetime]] = {}
    for captured_at, title in samples:
        reason = flag_for_title(title)
        if reason is not None:
            seen.setdefault(reason, []).append(datetime.fromisoformat(captured_at).astimezone(tz))
    return [
        FlagSummary(reason, len(times), len(times) * minutes_per_sample, _sessions(times, session_gap))
        for reason, times in seen.items()
    ]


def _sessions(times: list[datetime], gap: timedelta) -> tuple[tuple[datetime, datetime], ...]:
    """Split sorted sample times into ``(first, last)`` runs at gaps over ``gap``."""
    runs = [[times[0], times[0]]]
    for time in times[1:]:
        if time - runs[-1][1] > gap:
            runs.append([time, time])
        else:
            runs[-1][1] = time
    return tuple((first, last) for first, last in runs)
