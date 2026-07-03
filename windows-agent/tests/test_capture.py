from windows_agent.capture import is_mostly_black, match_monitor_index

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


# is_mostly_black gates the DXGI fallback: a pure-black mss frame (what an
# exclusive-fullscreen game produces) should trigger it, a rendered frame not.
FRAME_PIXELS = 200 * 200


def test_all_black_frame_is_detected():
    assert is_mostly_black(b"\x00\x00\x00" * FRAME_PIXELS) is True


def test_bright_frame_is_not_black():
    assert is_mostly_black(b"\xff\xff\xff" * FRAME_PIXELS) is False


def test_dark_but_rendered_frame_is_not_black():
    # A dim grey screen (value 40) is above the threshold, so it's not "black"
    # and won't waste a DXGI capture.
    assert is_mostly_black(b"\x28\x28\x28" * FRAME_PIXELS) is False


def test_near_black_below_threshold_counts_as_black():
    # Sensor/encoding noise a few levels above zero still reads as black.
    assert is_mostly_black(b"\x02\x01\x03" * FRAME_PIXELS) is True


def test_single_bright_region_is_not_black():
    # A frame that's black except for a lit patch is a real (partly dark) frame.
    frame = bytearray(b"\x00\x00\x00" * FRAME_PIXELS)
    for i in range(3 * (FRAME_PIXELS - 500), len(frame)):
        frame[i] = 200
    assert is_mostly_black(bytes(frame)) is False


def test_empty_buffer_is_not_black():
    assert is_mostly_black(b"") is False
