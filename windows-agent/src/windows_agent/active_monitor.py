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


def set_dpi_awareness() -> None:
    """Make the process per-monitor DPI aware, so win32 and mss report monitor
    geometry in the same (physical) pixel units.

    Without this, under display scaling win32's GetMonitorInfo and mss report
    different monitor rects and the two fail to line up. Must run before the
    first monitor query; safe to call more than once (later calls no-op or fail
    harmlessly once awareness is already set). No-ops off Windows.
    """
    if win32gui is None:
        return
    import ctypes

    for setter in (
        # Win10 1703+: per-monitor v2 (DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4)
        lambda: ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)),
        # Win8.1+: per-monitor (PROCESS_PER_MONITOR_DPI_AWARE = 2)
        lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2),
        # Vista+: system DPI aware
        lambda: ctypes.windll.user32.SetProcessDPIAware(),
    ):
        try:
            setter()
            return
        except (AttributeError, OSError):
            continue


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
