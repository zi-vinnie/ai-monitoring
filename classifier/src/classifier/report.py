import argparse
import html
import logging
from datetime import date

from classifier.aggregate import CategorySummary, summarize, total_minutes
from classifier.chart import format_duration, render_chart
from classifier.config import ReportConfig, load_report_config
from classifier.db import count_failed_polls, fetch_labels, get_connection
from classifier.emailer import chart_cid, send_email
from classifier.timeframe import day_bounds_utc, parse_date, resolve_tz

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DISPLAY_NAMES: dict[str, str] = {
    "productive": "Productive",
    "gaming": "Gaming",
    "video_entertainment": "Video / streaming",
    "social_media": "Social media",
    "browsing_other": "Web browsing",
    "unknown": "Unknown",
}


def _share(minutes: float, total: float) -> str:
    return f"{minutes / total * 100:.0f}%" if total else "0%"


def _ranked(summaries: list[CategorySummary]) -> list[CategorySummary]:
    """Non-empty categories, largest first (what a reader actually cares about)."""
    return sorted((s for s in summaries if s.minutes > 0), key=lambda s: s.minutes, reverse=True)


def build_text_body(
    summaries: list[CategorySummary], total: float, day_label: str, failed_polls: int
) -> str:
    lines = [f"Screen-time summary — {day_label}", f"Total tracked: {format_duration(total)}", ""]
    for summary in _ranked(summaries):
        name = _DISPLAY_NAMES[summary.category]
        lines.append(f"  {name:<20} {format_duration(summary.minutes):>8}   {_share(summary.minutes, total):>4}")
    if failed_polls:
        lines += ["", f"Note: {failed_polls} poll(s) failed this day, so some activity may be unrecorded."]
    lines += ["", "Times are estimated from screenshots sampled at the poll interval."]
    return "\n".join(lines)


def build_html_body(
    summaries: list[CategorySummary], total: float, day_label: str, failed_polls: int, cid: str
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
        '<div style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;color:#0b0b0b;max-width:640px;">'
        f'<h2 style="margin:0 0 4px;">Screen-time summary</h2>'
        f'<p style="margin:0 0 16px;color:#52514e;">{html.escape(day_label)} · total tracked '
        f"<strong>{format_duration(total)}</strong></p>"
        f'<img src="cid:{cid}" alt="Screen time by activity" style="max-width:100%;height:auto;margin-bottom:16px;">'
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
    parser.add_argument("--date", help="Day to report as YYYY-MM-DD (default: today in REPORT_TZ)")
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
        labels = fetch_labels(conn, start_iso, end_iso)
        failed_polls = count_failed_polls(conn, start_iso, end_iso)
    finally:
        conn.close()

    summaries = summarize(labels, config.poll_interval_minutes)
    total = total_minutes(summaries)

    if total <= 0:
        logger.info("No labelled activity for %s; sending an empty-day notice", day.isoformat())
        text_body, html_body = build_empty_body(day_label, failed_polls)
        _send(config, day, text_body, html_body, None)
        return

    image_png = render_chart(summaries, day_label)
    text_body = build_text_body(summaries, total, day_label, failed_polls)
    html_body = build_html_body(summaries, total, day_label, failed_polls, chart_cid())
    _send(config, day, text_body, html_body, image_png)


def _send(config: ReportConfig, day: date, text_body: str, html_body: str, image_png: bytes | None) -> None:
    send_email(config, f"Screen-time summary — {day.isoformat()}", text_body, html_body, image_png)
    logger.info("Sent report for %s to %s", day.isoformat(), ", ".join(config.email_to))


def main() -> None:
    run()


if __name__ == "__main__":
    main()
