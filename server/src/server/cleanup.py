import argparse
import logging
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

from server.config import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Screenshots are saved under SCREENSHOT_DIR/<YYYY-MM-DD>/ (UTC date), so
# retention is enforced per day directory: anything older than the retention
# window is removed wholesale. The `screenshots` rows (and their labels) in
# SQLite are deliberately left untouched — only the image bytes are dropped.


def _parse_day(name: str) -> date | None:
    try:
        return date.fromisoformat(name)
    except ValueError:
        return None


def expired_day_dirs(screenshot_dir: Path, today: date, retention_days: int) -> list[Path]:
    """Return the day directories under `screenshot_dir` older than the retention window.

    A directory is kept if its date is within the last `retention_days` days,
    counting `today` as day 1 — so with `retention_days=7` the seven most
    recent calendar days survive. Directories whose name isn't a `YYYY-MM-DD`
    date are ignored (never deleted). Pure function, unit-testable.
    """
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")
    if not screenshot_dir.is_dir():
        return []
    expired = []
    for entry in sorted(screenshot_dir.iterdir()):
        if not entry.is_dir():
            continue
        day = _parse_day(entry.name)
        if day is None:
            continue
        if (today - day).days >= retention_days:
            expired.append(entry)
    return expired


def run() -> None:
    """Delete screenshot image directories older than RETENTION_DAYS.

    Single-shot entry point, meant to run once a day from a systemd timer.
    Keeps the SQLite rows and labels; only the PNGs go.
    """
    parser = argparse.ArgumentParser(description="Delete screenshots older than the retention window.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="list the directories that would be deleted without removing anything",
    )
    args = parser.parse_args()

    config = load_config()
    today = datetime.now(timezone.utc).date()
    expired = expired_day_dirs(config.screenshot_dir, today, config.retention_days)

    if not expired:
        logger.info("Nothing to delete (retention %d days)", config.retention_days)
        return

    for day_dir in expired:
        if args.dry_run:
            logger.info("Would delete %s", day_dir)
            continue
        shutil.rmtree(day_dir)
        logger.info("Deleted %s", day_dir)
