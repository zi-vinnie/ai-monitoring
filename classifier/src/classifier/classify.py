import argparse
import logging
import sqlite3
from pathlib import Path

import requests

from classifier.categories import LABEL_FORMAT, build_prompt, parse_label
from classifier.config import ClassifyConfig, load_classify_config
from classifier.db import fetch_unlabeled, get_connection, set_label
from classifier.images import encode_image
from classifier.ollama_client import classify_image
from classifier.timeframe import day_bounds_utc, parse_date, resolve_tz

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def classify_one(config: ClassifyConfig, row: sqlite3.Row) -> str | None:
    """Label a single screenshot row, or None if it can't be classified."""
    file_path = Path(row["file_path"])
    if not file_path.exists():
        # Retention may have deleted the image while its metadata row lingers.
        logger.warning("Screenshot file missing, skipping id=%s: %s", row["id"], file_path)
        return None
    image_b64 = encode_image(file_path, config.image_max_edge)
    prompt = build_prompt(row["window_title"])
    raw = classify_image(
        config.ollama_url,
        config.ollama_model,
        prompt,
        image_b64,
        LABEL_FORMAT,
        config.request_timeout,
    )
    label = parse_label(raw)
    if label is None:
        logger.warning("Unrecognized model output for id=%s: %r", row["id"], raw)
    return label


def run(argv: list[str] | None = None) -> None:
    """Classify the day's unlabeled screenshots with the local Ollama model.

    Single-shot entry point, meant to run once daily (cron / systemd timer)
    after the day's polling is done.
    """
    parser = argparse.ArgumentParser(
        description="Label the day's screenshots with a local Ollama vision model."
    )
    parser.add_argument("--date", help="Day to classify as YYYY-MM-DD (default: today in REPORT_TZ)")
    args = parser.parse_args(argv)

    config = load_classify_config()
    tz = resolve_tz(config.report_tz)
    day = parse_date(args.date, tz)
    start_iso, end_iso = day_bounds_utc(day, tz)

    conn = get_connection(config.db_path)
    try:
        rows = fetch_unlabeled(conn, start_iso, end_iso)
        logger.info("Classifying %d unlabeled screenshot(s) for %s", len(rows), day.isoformat())
        labeled = 0
        for row in rows:
            try:
                label = classify_one(config, row)
            except requests.RequestException as exc:
                # Ollama unreachable / model missing / timeout — skip this image
                # (it stays unlabeled, so a later run retries it) rather than
                # aborting the whole batch.
                logger.warning("Ollama request failed for id=%s: %s", row["id"], exc)
                continue
            if label is not None:
                set_label(conn, row["id"], label)
                labeled += 1
                logger.info("id=%s -> %s (window=%r)", row["id"], label, row["window_title"])
        logger.info("Labeled %d of %d screenshot(s) for %s", labeled, len(rows), day.isoformat())
    finally:
        conn.close()


def main() -> None:
    run()


if __name__ == "__main__":
    main()
