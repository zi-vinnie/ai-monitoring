import base64
import logging
from datetime import datetime, timezone

import requests

from server.config import Config, load_config
from server.db import get_connection, insert_agent_status, insert_screenshot
from server.fetch import fetch_screenshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)
# urllib3 logs each request line at DEBUG, which would put the heartbeat's
# push token in the journal if the root level were ever lowered.
logging.getLogger("urllib3").setLevel(logging.INFO)

# Window titles that are pure noise: skip storing them entirely to save space.
# The lock screen carries no activity signal and can't be reviewed later, so
# there's nothing worth keeping. (The bare desktop — "Program Manager" or a null
# title — IS stored and labelled `idle` by the classifier, so it still shows on
# the timeline; only the lock screen is dropped outright.)
SKIP_WINDOW_TITLES = {"Windows Default Lock Screen"}


def _record_status(config: Config, status: str, detail: str) -> None:
    conn = get_connection(config.db_path)
    try:
        insert_agent_status(conn, datetime.now(timezone.utc).isoformat(), status, detail)
    finally:
        conn.close()


def _send_heartbeat(config: Config) -> None:
    """Tell the health dashboard the agent answered. Never fails the poll."""
    if not config.heartbeat_url:
        return
    try:
        requests.get(config.heartbeat_url, timeout=10).raise_for_status()
    except Exception as exc:
        # Broad on purpose: a malformed URL can raise urllib3 errors that
        # aren't RequestExceptions. The URL holds the push token, so log only
        # the exception type.
        logger.warning("Heartbeat failed: %s", type(exc).__name__)


def run() -> None:
    """Fetch the current screenshot from the Windows agent and save it.

    Single-shot entry point, meant to be invoked on a schedule (a systemd
    timer) every 10 minutes rather than looping internally.
    """
    config = load_config()

    try:
        payload = fetch_screenshot(config.agent_url, config.agent_api_key)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        # Laptop off/asleep or firewalled: an expected, routine condition.
        logger.warning("Windows agent unreachable: %s", exc)
        _record_status(config, "unreachable", str(exc))
        return
    except requests.exceptions.RequestException as exc:
        # Reachable but the request failed, e.g. the agent returned 500 because
        # capture raised (locked/off screen), or 401 for a bad API key. Don't
        # crash a scheduled run over it — log and record, then exit cleanly.
        logger.warning("Windows agent request failed: %s", exc)
        _record_status(config, "error", str(exc))
        return

    captured_at_raw = payload.get("captured_at")
    captured_dt = datetime.fromisoformat(captured_at_raw) if captured_at_raw else datetime.now(timezone.utc)
    captured_at = captured_dt.isoformat()

    monitor_index = payload["monitor_index"]
    window_title = payload.get("window_title")

    if window_title in SKIP_WINDOW_TITLES:
        # Don't waste storage/DB rows on the lock screen.
        # The agent still answered, so this counts as a healthy poll.
        logger.info("Skipping screenshot for window %r (in skip list)", window_title)
        _send_heartbeat(config)
        return

    image_bytes = base64.b64decode(payload["png_base64"])

    day_dir = config.screenshot_dir / captured_dt.strftime("%Y-%m-%d")
    day_dir.mkdir(parents=True, exist_ok=True)
    file_path = day_dir / f"{captured_dt.strftime('%Y%m%dT%H%M%SZ')}_monitor{monitor_index}.png"
    file_path.write_bytes(image_bytes)

    conn = get_connection(config.db_path)
    try:
        insert_screenshot(conn, captured_at, monitor_index, window_title, str(file_path))
        logger.info("Saved %s (window=%r)", file_path, window_title)
    finally:
        conn.close()

    _send_heartbeat(config)


if __name__ == "__main__":
    run()
