from zoneinfo import ZoneInfo

from classifier.flags import flag_for_title, summarize_flags


def test_flag_for_title_catches_stranger_video_chat():
    assert flag_for_title("OmeTV Video Chat — Omegle Random Cam Chat Alternative 2026 - Google Chrome")
    assert flag_for_title("Omegle: Talk to Strangers! Trusted Video Chat Alternative - Google Chrome")
    assert flag_for_title("Monkey: Random Video Chat | Talk to Strangers Instantly - Google Chrome")


def test_flag_for_title_ignores_videos_and_ordinary_titles():
    assert flag_for_title("chad and stacy go on omegle (nobody could handle it) - YouTube - Google Chrome") is None
    assert flag_for_title("WhatsApp") is None
    assert flag_for_title(None) is None


def test_summarize_flags_totals_and_local_times():
    samples = [
        ("2026-10-02T20:00:00+00:00", "OmeTV Video Chat - Google Chrome"),
        ("2026-10-02T20:10:00+00:00", "WhatsApp"),
        ("2026-10-02T20:20:00+00:00", "OmeTV Video Chat - Google Chrome"),
    ]
    [flag] = summarize_flags(samples, ZoneInfo("Europe/London"), 10)
    assert flag.count == 2
    assert flag.minutes == 20
    assert [(f"{a:%H:%M}", f"{b:%H:%M}") for a, b in flag.sessions] == [("21:00", "21:20")]  # BST


def test_summarize_flags_splits_separate_sessions():
    samples = [
        ("2026-09-29T23:10:00+00:00", "OmeTV Video Chat - Google Chrome"),  # 00:10 BST
        ("2026-09-29T23:20:00+00:00", "OmeTV Video Chat - Google Chrome"),
        ("2026-09-30T20:50:00+00:00", "OmeTV Video Chat - Google Chrome"),  # 21:50 BST
    ]
    [flag] = summarize_flags(samples, ZoneInfo("Europe/London"), 10)
    assert [(f"{a:%H:%M}", f"{b:%H:%M}") for a, b in flag.sessions] == [("00:10", "00:20"), ("21:50", "21:50")]
