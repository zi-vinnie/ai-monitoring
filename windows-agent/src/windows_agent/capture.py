import base64

import mss
import mss.tools

from windows_agent.active_monitor import get_active_monitor_rect, get_active_window_title


def match_monitor_index(rect: tuple[int, int, int, int], monitors: list[dict]) -> int:
    """Match a win32 monitor rect to its index in mss's monitor list.

    mss.monitors[0] is the combined virtual screen spanning all monitors, so
    real monitors start at index 1.
    """
    left, top, right, bottom = rect
    width, height = right - left, bottom - top
    for index, monitor in enumerate(monitors):
        if index == 0:
            continue
        if (monitor["left"], monitor["top"], monitor["width"], monitor["height"]) == (left, top, width, height):
            return index
    raise RuntimeError("Could not match the active window's monitor to an mss monitor")


def capture_active_monitor() -> dict:
    """Capture whichever monitor currently holds the focused window.

    Falls back to monitor 1 if there's no focused window (e.g. desktop
    clicked, or running outside a normal desktop session).
    """
    rect = get_active_monitor_rect()
    with mss.mss() as sct:
        monitor_index = match_monitor_index(rect, sct.monitors) if rect is not None else 1
        monitor = sct.monitors[monitor_index]
        shot = sct.grab(monitor)
        png_bytes = mss.tools.to_png(shot.rgb, shot.size)

    return {
        "monitor_index": monitor_index,
        "window_title": get_active_window_title(),
        "png_base64": base64.b64encode(png_bytes).decode(),
    }
