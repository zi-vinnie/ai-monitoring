import base64
import logging
from datetime import datetime, timezone

from server.config import load_config
from server.db import get_connection, insert_screenshot
from server.fetch import fetch_screenshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run() -> None:
    """Fetch the current screenshot from the Windows agent and save it.

    Single-shot entry point, meant to be invoked on a schedule (cron or a
    systemd timer) every 10-15 minutes rather than looping internally.
    """
    config = load_config()
    payload = fetch_screenshot(config.agent_url, config.agent_api_key)

    captured_at_raw = payload.get("captured_at")
    captured_dt = datetime.fromisoformat(captured_at_raw) if captured_at_raw else datetime.now(timezone.utc)
    captured_at = captured_dt.isoformat()

    monitor_index = payload["monitor_index"]
    window_title = payload.get("window_title")
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


if __name__ == "__main__":
    run()
