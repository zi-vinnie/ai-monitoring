from windows_agent.capture import match_monitor_index

# mss.monitors[0] is the combined virtual screen; real monitors start at index 1.
TWO_MONITORS = [
    {"left": 0, "top": 0, "width": 3840, "height": 2160},   # 0: virtual (both)
    {"left": 0, "top": 0, "width": 1920, "height": 1080},   # 1: left
    {"left": 1920, "top": 0, "width": 1920, "height": 1080},  # 2: right
]


def test_exact_match_left_monitor():
    assert match_monitor_index((0, 0, 1920, 1080), TWO_MONITORS) == 1


def test_exact_match_right_monitor():
    assert match_monitor_index((1920, 0, 3840, 1080), TWO_MONITORS) == 2


def test_tolerates_scaling_rounding_offsets():
    # win32 rect a few px off from mss's (as happens under DPI scaling) still
    # resolves to the monitor it mostly overlaps.
    assert match_monitor_index((1922, 1, 3838, 1079), TWO_MONITORS) == 2


def test_picks_monitor_with_greatest_overlap_when_straddling():
    # A rect spanning the seam but mostly on the right monitor picks the right.
    assert match_monitor_index((1000, 0, 3840, 1080), TWO_MONITORS) == 2


def test_raises_when_no_overlap_with_any_monitor():
    try:
        match_monitor_index((10000, 10000, 11000, 11000), TWO_MONITORS)
    except RuntimeError:
        return
    raise AssertionError("expected RuntimeError when the rect overlaps no monitor")
