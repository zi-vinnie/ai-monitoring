from datetime import date
from pathlib import Path

import pytest

from server.cleanup import expired_day_dirs


def _mkdirs(root: Path, names: list[str]) -> None:
    for name in names:
        (root / name).mkdir()


def test_keeps_last_seven_days_including_today(tmp_path: Path) -> None:
    _mkdirs(tmp_path, ["2026-09-04", "2026-09-05", "2026-09-06", "2026-09-11", "2026-09-12"])
    expired = expired_day_dirs(tmp_path, today=date(2026, 9, 12), retention_days=7)
    assert [p.name for p in expired] == ["2026-09-04", "2026-09-05"]


def test_ignores_non_date_entries(tmp_path: Path) -> None:
    _mkdirs(tmp_path, ["2020-01-01", "not-a-date", "misc"])
    (tmp_path / "stray.png").write_bytes(b"")
    expired = expired_day_dirs(tmp_path, today=date(2026, 9, 12), retention_days=7)
    assert [p.name for p in expired] == ["2020-01-01"]


def test_missing_dir_returns_nothing(tmp_path: Path) -> None:
    assert expired_day_dirs(tmp_path / "nope", today=date(2026, 9, 12), retention_days=7) == []


def test_rejects_zero_retention(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        expired_day_dirs(tmp_path, today=date(2026, 9, 12), retention_days=0)
