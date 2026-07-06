import argparse
import html
import logging
from datetime import date

from classifier.aggregate import CategorySummary, summarize, total_minutes
from classifier.chart import format_duration, render_timeline
from classifier.config import ReportConfig, load_report_config
from classifier.db import count_failed_polls, fetch_labeled_events, get_connection
from classifier.emailer import chart_cid, send_email
from classifier.timeframe import day_bounds_utc, parse_date, resolve_tz
from classifier.timeline import TimelineBlock, active_span, build_timeline, format_clock

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DISPLAY_NAMES: dict[str, str] = {
    "productive": "Productive",
    "gaming": "Gaming",
    "video_entertainment": "Video / streaming",
    "social_media": "Social media",
    "browsing": "Web browsing",
    "unknown": "Unknown",
}


def _share(minutes: float, total: float) -> str:
    return f"{minutes / total * 100:.0f}%" if total else "0%"


def _ranked(summaries: list[CategorySummary]) -> list[CategorySummary]:
    """Non-empty categories, largest first (what a reader actually cares about)."""
    return sorted((s for s in summaries if s.minutes > 0), key=lambda s: s.minutes, reverse=True)


def _productive_minutes(summaries: list[CategorySummary]) -> float:
    return next((s.minutes for s in summaries if s.category == "productive"), 0.0)


def _span_label(blocks: list[TimelineBlock]) -> str | None:
    span = active_span(blocks)
    return f"{format_clock(span[0])} – {format_clock(span[1])}" if span else None


def build_text_body(
    summaries: list[CategorySummary],
    total: float,
    day_label: str,
    failed_polls: int,
    blocks: list[TimelineBlock],
) -> str:
    lines = [f"Screen-time summary — {day_label}", ""]
    lines.append(f"Screen time:    {format_duration(total)}")
    lines.append(f"Productive:     {_share(_productive_minutes(summaries), total)} of screen time")
    span = _span_label(blocks)
    if span:
        lines.append(f"Active window:  {span}")
    lines += ["", "By activity:"]
    for summary in _ranked(summaries):
        name = _DISPLAY_NAMES[summary.category]
        lines.append(f"  {name:<20} {format_duration(summary.minutes):>8}   {_share(summary.minutes, total):>4}")
    if failed_polls:
        lines += ["", f"Note: {failed_polls} poll(s) failed this day, so some activity may be unrecorded."]
    lines += ["", "Times are estimated from screenshots sampled at the poll interval."]
    return "\n".join(lines)


def _stat_tiles(summaries: list[CategorySummary], total: float, blocks: list[TimelineBlock]) -> str:
    """A small row of headline numbers: screen time, productive share, active window."""
    tiles = [
        ("Screen time", format_duration(total)),
        ("Productive", _share(_productive_minutes(summaries), total)),
    ]
    span = _span_label(blocks)
    if span:
        tiles.append(("Active window", span))
    cells = "".join(
        '<td style="padding:0 24px 0 0;vertical-align:top;">'
        f'<div style="color:#898781;font-size:12px;text-transform:uppercase;letter-spacing:0.04em;">{html.escape(caption)}</div>'
        f'<div style="color:#0b0b0b;font-size:22px;font-weight:700;font-variant-numeric:tabular-nums;">{html.escape(value)}</div>'
        "</td>"
        for caption, value in tiles
    )
    return f'<table style="border-collapse:collapse;margin:0 0 18px;"><tr>{cells}</tr></table>'


def build_html_body(
    summaries: list[CategorySummary],
    total: float,
    day_label: str,
    failed_polls: int,
    blocks: list[TimelineBlock],
    cid: str,
) -> str:
    rows = "".join(
        f'<tr><td style="padding:4px 16px 4px 0;">{html.escape(_DISPLAY_NAMES[s.category])}</td>'
        f'<td style="padding:4px 16px 4px 0;text-align:right;font-variant-numeric:tabular-nums;">'
        f"{format_duration(s.minutes)}</td>"
        f'<td style="padding:4px 0;text-align:right;color:#52514e;font-variant-numeric:tabular-nums;">'
        f"{_share(s.minutes, total)}</td></tr>"
        for s in _ranked(summaries)
    )
    note = (
        f'<p style="color:#b45309;font-size:13px;">Note: {failed_polls} poll(s) failed this day, '
        "so some activity may be unrecorded.</p>"
        if failed_polls
        else ""
    )
    return (
        '<div style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;color:#0b0b0b;max-width:720px;">'
        f'<h2 style="margin:0 0 4px;">Screen-time summary</h2>'
        f'<p style="margin:0 0 16px;color:#52514e;">{html.escape(day_label)}</p>'
        f'<img src="cid:{cid}" alt="Activity through the day" style="max-width:100%;height:auto;margin-bottom:18px;">'
        f"{_stat_tiles(summaries, total, blocks)}"
        f'<table style="border-collapse:collapse;font-size:14px;">{rows}</table>'
        f"{note}"
        '<p style="color:#898781;font-size:12px;margin-top:16px;">'
        "Times are estimated from screenshots sampled at the poll interval.</p>"
        "</div>"
    )


def build_empty_body(day_label: str, failed_polls: int) -> tuple[str, str]:
    reason = (
        f" All {failed_polls} poll(s) that ran failed, so the machine was likely off or unreachable."
        if failed_polls
        else " No screenshots were labelled for this day."
    )
    text = f"Screen-time summary — {day_label}\n\nNo activity recorded.{reason}"
    html_body = (
        '<div style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;color:#0b0b0b;">'
        f"<h2>Screen-time summary — {html.escape(day_label)}</h2>"
        f"<p>No activity recorded.{html.escape(reason)}</p></div>"
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
    args = parser.parse_args(argv)

    config = load_report_config()
    if not config.email_to:
        raise SystemExit("EMAIL_TO is empty — set at least one recipient in .env")

    tz = resolve_tz(config.report_tz)
    day = parse_date(args.date, tz)
    start_iso, end_iso = day_bounds_utc(day, tz)
    day_label = day.strftime("%A, %d %b %Y")

    conn = get_connection(config.db_path)
    try:
        events = fetch_labeled_events(conn, start_iso, end_iso)
        failed_polls = count_failed_polls(conn, start_iso, end_iso)
    finally:
        conn.close()

    summaries = summarize([label for _, label in events], config.poll_interval_minutes)
    total = total_minutes(summaries)

    if total <= 0:
        logger.info("No labelled activity for %s; sending an empty-day notice", day.isoformat())
        text_body, html_body = build_empty_body(day_label, failed_polls)
        _send(config, day, text_body, html_body, None)
        return

    blocks = build_timeline(events, tz, config.poll_interval_minutes)
    image_png = render_timeline(blocks, day_label)
    text_body = build_text_body(summaries, total, day_label, failed_polls, blocks)
    html_body = build_html_body(summaries, total, day_label, failed_polls, blocks, chart_cid())
    _send(config, day, text_body, html_body, image_png)


def _send(config: ReportConfig, day: date, text_body: str, html_body: str, image_png: bytes | None) -> None:
    send_email(config, f"Screen-time summary — {day.isoformat()}", text_body, html_body, image_png)
    logger.info("Sent report for %s to %s", day.isoformat(), ", ".join(config.email_to))


def main() -> None:
    run()


if __name__ == "__main__":
    main()
