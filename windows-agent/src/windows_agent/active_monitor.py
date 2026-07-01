"""Active window/monitor detection. Windows-only (pywin32)."""

try:
    import win32api
    import win32con
    import win32gui
except ImportError:  # pragma: no cover - pywin32 is only installable on Windows
    win32api = win32con = win32gui = None


def _require_windows() -> None:
    if win32gui is None:
        raise RuntimeError("Active window detection requires Windows (pywin32 not available)")


def get_active_window_title() -> str | None:
    _require_windows()
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None
    return win32gui.GetWindowText(hwnd) or None


def get_active_monitor_rect() -> tuple[int, int, int, int] | None:
    """Return (left, top, right, bottom) of the monitor containing the focused window."""
    _require_windows()
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None
    h_monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
    return win32api.GetMonitorInfo(h_monitor)["Monitor"]
