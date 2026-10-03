import argparse
import html
import logging
from dataclasses import dataclass
from datetime import date, timedelta

from classifier.aggregate import CategorySummary, active_minutes, summarize, total_minutes
from classifier.categories import IDLE
from classifier.chart import format_duration, render_range_timeline, render_timeline
from classifier.config import ReportConfig, load_report_config
from classifier.db import fetch_flag_candidates, fetch_labeled_events, get_connection
from classifier.emailer import chart_cid, send_email
from classifier.timeframe import day_bounds_utc, parse_date, resolve_tz
from classifier.flags import FlagSummary, summarize_flags
from classifier.timeline import TimelineBlock, build_timeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DISPLAY_NAMES: dict[str, str] = {
    "productive": "Productive",
    "gaming": "Gaming",
    "video_entertainment": "Video / streaming",
    "social_media": "Social media",
    "browsing": "Web browsing",
    "idle": "Idle",
}


def _share(minutes: float, total: float) -> str:
    return f"{minutes / total * 100:.0f}%" if total else "0%"


def _ranked(summaries: list[CategorySummary]) -> list[CategorySummary]:
    """Non-empty active categories, largest first; idle is listed separately."""
    return sorted(
        (s for s in summaries if s.minutes > 0 and s.category != IDLE),
        key=lambda s: s.minutes,
        reverse=True,
    )


def _idle_summary(summaries: list[CategorySummary]) -> CategorySummary | None:
    """The idle bucket if any idle time was recorded, else None."""
    return next((s for s in summaries if s.category == IDLE and s.minutes > 0), None)


def _productive_minutes(summaries: list[CategorySummary]) -> float:
    return next((s.minutes for s in summaries if s.category == "productive"), 0.0)


def _flag_line(flag: FlagSummary, with_day: bool = False) -> str:
    """'about 1h 20m (00:10–00:40, 21:30–23:40)', optionally prefixed with the day."""
    span = ", ".join(
        f"{first:%H:%M}" if first == last else f"{first:%H:%M}–{last:%H:%M}" for first, last in flag.sessions
    )
    day = f"{flag.first_seen:%a %d %b}: " if with_day else ""
    return f"{day}about {format_duration(flag.minutes)} ({span})"


def _flags_text(flags_by_reason: dict[str, list[FlagSummary]], with_day: bool = False) -> list[str]:
    if not flags_by_reason:
        return []
    lines = ["", "Worth a look:"]
    for reason, flags in flags_by_reason.items():
        lines.append(f"  {reason}")
        lines += [f"    {_flag_line(flag, with_day)}" for flag in flags]
    return lines


def _flags_html(flags_by_reason: dict[str, list[FlagSummary]], with_day: bool = False) -> str:
    """A highlighted callout listing each flagged activity and when it was seen."""
    if not flags_by_reason:
        return ""
    items = "".join(
        f'<p style="margin:6px 0 2px;font-weight:600;">{html.escape(reason)}</p>'
        + "".join(f'<div style="margin-left:12px;">{html.escape(_flag_line(flag, with_day))}</div>' for flag in flags)
        for reason, flags in flags_by_reason.items()
    )
    return (
        '<div style="border-left:4px solid #d03b3b;background:#fbefee;padding:10px 14px;margin:0 0 18px;">'
        '<div style="font-weight:700;color:#a02626;">Worth a look</div>'
        f"{items}</div>"
    )


def _group_flags(flags: list[FlagSummary]) -> dict[str, list[FlagSummary]]:
    grouped: dict[str, list[FlagSummary]] = {}
    for flag in flags:
        grouped.setdefault(flag.reason, []).append(flag)
    return grouped


def build_text_body(
    summaries: list[CategorySummary],
    active: float,
    day_label: str,
    flags: dict[str, list[FlagSummary]] | None = None,
) -> str:
    lines = [f"Screen-time summary — {day_label}", ""]
    lines.append(f"Screen time:    {format_duration(active)}")
    lines.append(f"Productive:     {_share(_productive_minutes(summaries), active)} of screen time")
    lines += ["", "By activity:"]
    for summary in _ranked(summaries):
        name = _DISPLAY_NAMES[summary.category]
        lines.append(f"  {name:<20} {format_duration(summary.minutes):>8}   {_share(summary.minutes, active):>4}")
    idle = _idle_summary(summaries)
    if idle:
        # Idle is excluded from the totals above, so it carries no share (—).
        lines.append(f"  {_DISPLAY_NAMES[IDLE]:<20} {format_duration(idle.minutes):>8}   {'—':>4}")
    lines += _flags_text(flags or {})
    lines += ["", "Times are estimated from screenshots sampled at the poll interval."]
    return "\n".join(lines)


def _stat_tiles(summaries: list[CategorySummary], active: float) -> str:
    """A small row of headline numbers: screen time and productive share."""
    return _tiles_html(
        [
            ("Screen time", format_duration(active)),
            ("Productive", _share(_productive_minutes(summaries), active)),
        ]
    )


def _tiles_html(tiles: list[tuple[str, str]]) -> str:
    """A row of ``(caption, value)`` headline numbers."""
    cells = "".join(
        '<td style="padding:0 24px 0 0;vertical-align:top;">'
        f'<div style="color:#898781;font-size:12px;text-transform:uppercase;letter-spacing:0.04em;">{html.escape(caption)}</div>'
        f'<div style="color:#0b0b0b;font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;">{html.escape(value)}</div>'
        "</td>"
        for caption, value in tiles
    )
    return f'<table style="border-collapse:collapse;margin:0 0 18px;"><tr>{cells}</tr></table>'


def _table_row(name: str, minutes: float, share: str) -> str:
    return (
        f'<tr><td style="padding:4px 16px 4px 0;">{html.escape(name)}</td>'
        f'<td style="padding:4px 16px 4px 0;text-align:right;font-variant-numeric:tabular-nums;">'
        f"{format_duration(minutes)}</td>"
        f'<td style="padding:4px 0;text-align:right;color:#52514e;font-variant-numeric:tabular-nums;">'
        f"{share}</td></tr>"
    )


def build_html_body(
    summaries: list[CategorySummary],
    active: float,
    day_label: str,
    cid: str,
    flags: dict[str, list[FlagSummary]] | None = None,
) -> str:
    rows = "".join(
        _table_row(_DISPLAY_NAMES[s.category], s.minutes, _share(s.minutes, active))
        for s in _ranked(summaries)
    )
    idle = _idle_summary(summaries)
    if idle:
        # Idle is excluded from the totals above, so it carries no share (—).
        rows += _table_row(_DISPLAY_NAMES[IDLE], idle.minutes, "—")
    return (
        '<div style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;color:#0b0b0b;max-width:720px;">'
        f'<h2 style="margin:0 0 4px;">Screen-time summary</h2>'
        f'<p style="margin:0 0 16px;color:#52514e;">{html.escape(day_label)}</p>'
        f"{_flags_html(flags or {})}"
        f'<img src="cid:{cid}" alt="Activity through the day" style="max-width:100%;height:auto;margin-bottom:18px;">'
        f"{_stat_tiles(summaries, active)}"
        f'<table style="border-collapse:collapse;font-size:14px;">{rows}</table>'
        '<p style="color:#898781;font-size:12px;margin-top:16px;">'
        "Times are estimated from screenshots sampled at the poll interval.</p>"
        "</div>"
    )


def build_empty_body(day_label: str) -> tuple[str, str]:
    text = f"Screen-time summary — {day_label}\n\nNo activity recorded for this day."
    html_body = (
        '<div style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;color:#0b0b0b;">'
        f"<h2>Screen-time summary — {html.escape(day_label)}</h2>"
        "<p>No activity recorded for this day.</p></div>"
    )
    return text, html_body


def run(argv: list[str] | None = None) -> None:
    """Aggregate the day's labels, render a chart, and email the summary.

    Single-shot entry point, meant to run once daily after `classify-screenshots`.
    """
    parser = argparse.ArgumentParser(description="Email a daily screen-time summary with a chart.")
    parser.add_argument(
        "--date",
        help="Day to report: YYYY-MM-DD, 'today', or 'yesterday' (default: today in REPORT_TZ)",
    )
    parser.add_argument("--start", help="First day of a multi-day summary (YYYY-MM-DD); use with --end")
    parser.add_argument("--end", help="Last day (inclusive) of a multi-day summary (YYYY-MM-DD)")
    args = parser.parse_args(argv)
    if bool(args.start) != bool(args.end):
        parser.error("--start and --end must be given together")
    if args.start and args.date:
        parser.error("use either --date or --start/--end, not both")

    config = load_report_config()
    if not config.email_to:
        raise SystemExit("EMAIL_TO is empty — set at least one recipient in .env")

    tz = resolve_tz(config.report_tz)
    if args.start:
        start, end = parse_date(args.start, tz), parse_date(args.end, tz)
        if end < start:
            parser.error("--end is before --start")
        run_range(config, start, end)
        return
    day = parse_date(args.date, tz)
    start_iso, end_iso = day_bounds_utc(day, tz)
    day_label = day.strftime("%A, %d %b %Y")

    conn = get_connection(config.db_path)
    try:
        events = fetch_labeled_events(conn, start_iso, end_iso)
        flags = _group_flags(
            summarize_flags(fetch_flag_candidates(conn, start_iso, end_iso), tz, config.poll_interval_minutes)
        )
    finally:
        conn.close()

    summaries = summarize([label for _, label in events], config.poll_interval_minutes)
    recorded = total_minutes(summaries)  # any labelled sample, idle included

    if recorded <= 0:
        logger.info("No labelled activity for %s; sending an empty-day notice", day.isoformat())
        text_body, html_body = build_empty_body(day_label)
        _send(config, day, text_body, html_body, None)
        return

    # Headline screen time and shares are active use only — idle is broken out
    # separately (it still renders on the timeline and in the breakdown).
    active = active_minutes(summaries)
    blocks = build_timeline(events, tz, config.poll_interval_minutes)
    image_png = render_timeline(blocks, day_label)
    text_body = build_text_body(summaries, active, day_label, flags)
    html_body = build_html_body(summaries, active, day_label, chart_cid(), flags)
    _send(config, day, text_body, html_body, image_png)


def _send(config: ReportConfig, day: date, text_body: str, html_body: str, image_png: bytes | None) -> None:
    send_email(config, f"Screen-time summary — {day.isoformat()}", text_body, html_body, image_png)
    logger.info("Sent report for %s to %s", day.isoformat(), ", ".join(config.email_to))


# --- Multi-day summary (send-report --start ... --end ...) -------------------


@dataclass(frozen=True)
class DayData:
    """One day's slice of a multi-day summary."""

    day: date
    summaries: list[CategorySummary]
    blocks: list[TimelineBlock]
    flags: list[FlagSummary]

    @property
    def active(self) -> float:
        return active_minutes(self.summaries)

    @property
    def recorded(self) -> bool:
        """Whether any sample (idle included) was labelled — else the PC was off."""
        return total_minutes(self.summaries) > 0

    @property
    def label(self) -> str:
        return f"{self.day:%a %d %b}"

    def top_category(self) -> str:
        ranked = _ranked(self.summaries)
        return _DISPLAY_NAMES[ranked[0].category] if ranked else "—"


def _merge_summaries(days: list[DayData]) -> list[CategorySummary]:
    """Sum per-category counts and minutes across days, keeping canonical order."""
    merged = [CategorySummary(s.category, 0, 0.0) for s in days[0].summaries]
    for day in days:
        merged = [
            CategorySummary(m.category, m.count + s.count, m.minutes + s.minutes)
            for m, s in zip(merged, day.summaries)
        ]
    return merged


def build_range_text_body(days: list[DayData], range_label: str) -> str:
    totals = _merge_summaries(days)
    active = active_minutes(totals)
    with_data = [d for d in days if d.recorded]
    lines = [f"Screen-time summary — {range_label}", ""]
    lines.append(f"Total screen time:  {format_duration(active)}")
    if with_data:
        lines.append(f"Daily average:      {format_duration(active / len(with_data))} (over {len(with_data)} day(s) with data)")
    lines.append(f"Productive:         {_share(_productive_minutes(totals), active)} of screen time")
    lines += _flags_text(_group_flags([f for d in days for f in d.flags]), with_day=True)
    lines += ["", "By day:"]
    for d in days:
        if d.recorded:
            lines.append(f"  {d.label:<12} {format_duration(d.active):>8}   mostly {d.top_category()}")
        else:
            lines.append(f"  {d.label:<12} no data (PC off or offline)")
    lines += ["", "By activity (whole period):"]
    for summary in _ranked(totals):
        name = _DISPLAY_NAMES[summary.category]
        lines.append(f"  {name:<20} {format_duration(summary.minutes):>8}   {_share(summary.minutes, active):>4}")
    idle = _idle_summary(totals)
    if idle:
        lines.append(f"  {_DISPLAY_NAMES[IDLE]:<20} {format_duration(idle.minutes):>8}   {'—':>4}")
    lines += ["", "Times are estimated from screenshots sampled at the poll interval."]
    return "\n".join(lines)


def build_range_html_body(days: list[DayData], range_label: str, cid: str) -> str:
    totals = _merge_summaries(days)
    active = active_minutes(totals)
    with_data = [d for d in days if d.recorded]
    tiles = [("Total screen time", format_duration(active))]
    if with_data:
        tiles.append(("Daily average", format_duration(active / len(with_data))))
    tiles.append(("Productive", _share(_productive_minutes(totals), active)))
    day_rows = "".join(
        f'<tr><td style="padding:4px 16px 4px 0;">{html.escape(d.label)}</td>'
        + (
            f'<td style="padding:4px 16px 4px 0;text-align:right;font-variant-numeric:tabular-nums;">{format_duration(d.active)}</td>'
            f'<td style="padding:4px 0;color:#52514e;">mostly {html.escape(d.top_category())}</td>'
            if d.recorded
            else '<td colspan="2" style="padding:4px 0;color:#898781;">no data (PC off or offline)</td>'
        )
        + "</tr>"
        for d in days
    )
    cat_rows = "".join(
        _table_row(_DISPLAY_NAMES[s.category], s.minutes, _share(s.minutes, active)) for s in _ranked(totals)
    )
    idle = _idle_summary(totals)
    if idle:
        cat_rows += _table_row(_DISPLAY_NAMES[IDLE], idle.minutes, "—")
    h3 = '<h3 style="margin:18px 0 6px;font-size:15px;">'
    return (
        '<div style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;color:#0b0b0b;max-width:720px;">'
        '<h2 style="margin:0 0 4px;">Screen-time summary</h2>'
        f'<p style="margin:0 0 16px;color:#52514e;">{html.escape(range_label)}</p>'
        f"{_tiles_html(tiles)}"
        f"{_flags_html(_group_flags([f for d in days for f in d.flags]), with_day=True)}"
        f'<img src="cid:{cid}" alt="Activity by day" style="max-width:100%;height:auto;margin-bottom:8px;">'
        f'{h3}By day</h3><table style="border-collapse:collapse;font-size:14px;">{day_rows}</table>'
        f'{h3}By activity (whole period)</h3><table style="border-collapse:collapse;font-size:14px;">{cat_rows}</table>'
        '<p style="color:#898781;font-size:12px;margin-top:16px;">'
        "Times are estimated from screenshots sampled at the poll interval.</p>"
        "</div>"
    )


def collect_range(config: ReportConfig, start: date, end: date) -> list[DayData]:
    """Per-day summaries, timeline blocks and flags for ``start``..``end`` inclusive."""
    tz = resolve_tz(config.report_tz)
    interval = config.poll_interval_minutes
    conn = get_connection(config.db_path)
    try:
        days = []
        day = start
        while day <= end:
            start_iso, end_iso = day_bounds_utc(day, tz)
            events = fetch_labeled_events(conn, start_iso, end_iso)
            flags = summarize_flags(fetch_flag_candidates(conn, start_iso, end_iso), tz, interval)
            summaries = summarize([label for _, label in events], interval)
            days.append(DayData(day, summaries, build_timeline(events, tz, interval), flags))
            day += timedelta(days=1)
        return days
    finally:
        conn.close()


def range_label(start: date, end: date) -> str:
    return f"{start:%a %d %b} – {end:%a %d %b %Y}"


def run_range(config: ReportConfig, start: date, end: date) -> None:
    """Email one summary covering every day from ``start`` to ``end`` inclusive."""
    days = collect_range(config, start, end)
    label = range_label(start, end)
    image_png = render_range_timeline([(d.label, d.blocks) for d in days], f"Activity by day · {label}")
    text_body = build_range_text_body(days, label)
    html_body = build_range_html_body(days, label, chart_cid())
    subject = f"Screen-time summary — {start.isoformat()} to {end.isoformat()}"
    send_email(config, subject, text_body, html_body, image_png)
    logger.info("Sent summary for %s..%s to %s", start.isoformat(), end.isoformat(), ", ".join(config.email_to))


def main() -> None:
    run()


if __name__ == "__main__":
    main()
