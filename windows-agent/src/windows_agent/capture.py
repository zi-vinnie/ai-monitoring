import base64

import mss
import mss.tools

from windows_agent.active_monitor import get_active_monitor_rect, get_active_window_title


def match_monitor_index(rect: tuple[int, int, int, int], monitors: list[dict]) -> int:
    """Match a win32 monitor rect to its index in mss's monitor list.

    mss.monitors[0] is the combined virtual screen spanning all monitors, so
    real monitors start at index 1. Rather than requiring the win32 and mss
    rects to be exactly equal (which breaks under display scaling and pixel
    rounding), pick the mss monitor whose rect overlaps the win32 rect the most.
    """
    left, top, right, bottom = rect
    best_index, best_overlap = None, 0
    for index in range(1, len(monitors)):
        monitor = monitors[index]
        m_left, m_top = monitor["left"], monitor["top"]
        m_right, m_bottom = m_left + monitor["width"], m_top + monitor["height"]
        overlap_w = max(0, min(right, m_right) - max(left, m_left))
        overlap_h = max(0, min(bottom, m_bottom) - max(top, m_top))
        overlap = overlap_w * overlap_h
        if overlap > best_overlap:
            best_index, best_overlap = index, overlap
    if best_index is None:
        raise RuntimeError("Could not match the active window's monitor to an mss monitor")
    return best_index


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
        if png_bytes is None:
            raise RuntimeError("mss.tools.to_png returned no data")

    return {
        "monitor_index": monitor_index,
        "window_title": get_active_window_title(),
        "png_base64": base64.b64encode(png_bytes).decode(),
    }
