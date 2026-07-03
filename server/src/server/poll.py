import base64
import logging
from datetime import datetime, timezone

import requests

from server.config import Config, load_config
from server.db import get_connection, insert_agent_status, insert_screenshot
from server.diagnostics import diagnose_unreachable
from server.fetch import fetch_screenshot

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _record_status(config: Config, status: str, detail: str) -> None:
    conn = get_connection(config.db_path)
    try:
        insert_agent_status(conn, datetime.now(timezone.utc).isoformat(), status, detail)
    finally:
        conn.close()


def run() -> None:
    """Fetch the current screenshot from the Windows agent and save it.

    Single-shot entry point, meant to be invoked on a schedule (cron or a
    systemd timer) every 10-15 minutes rather than looping internally.
    """
    config = load_config()

    try:
        payload = fetch_screenshot(config.agent_url, config.agent_api_key)
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
        # No HTTP response at all (laptop off/asleep, agent stopped, Wi-Fi down).
        # All routine — probe the network with ICMP to record *which* one it was
        # instead of a bare "unreachable".
        status, detail = diagnose_unreachable(config.agent_url, config.router_ip)
        logger.warning("Windows agent unreachable (%s): %s [%s]", status, detail, exc)
        _record_status(config, status, detail)
        return
    except requests.exceptions.RequestException as exc:
        # We got an HTTP response but it wasn't a success, so the machine and
        # agent are reachable — the problem is at the application layer. A 401/403
        # means the API key was rejected (a permissions issue, not an outage);
        # anything else (e.g. 500 when capture raised on a locked screen) is a
        # generic error. Either way, don't crash a scheduled run — record and exit.
        response = getattr(exc, "response", None)
        code = getattr(response, "status_code", None)
        if code in (401, 403):
            detail = f"HTTP {code}: agent reachable but rejected the API key (permissions)"
            logger.warning("Windows agent %s", detail)
            _record_status(config, "unauthorized", detail)
        else:
            logger.warning("Windows agent request failed: %s", exc)
            _record_status(config, "error", str(exc))
        return

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
