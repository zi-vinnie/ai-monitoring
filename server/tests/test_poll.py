import base64
from pathlib import Path

import pytest
import requests

from server import poll
from server.config import Config

HEARTBEAT_URL = "http://kuma.test/api/push/token?status=up"


def _config(tmp_path: Path, heartbeat_url: str | None = HEARTBEAT_URL) -> Config:
    return Config(
        agent_url="http://agent.test:8000",
        agent_api_key="key",
        screenshot_dir=tmp_path / "screenshots",
        db_path=tmp_path / "metadata.sqlite3",
        retention_days=7,
        heartbeat_url=heartbeat_url,
    )


def _payload(window_title: str | None = "Notepad") -> dict:
    return {
        "captured_at": "2026-10-28T12:00:00+00:00",
        "monitor_index": 1,
        "window_title": window_title,
        "png_base64": base64.b64encode(b"png").decode(),
    }


@pytest.fixture
def heartbeats(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    class _Response:
        def raise_for_status(self) -> None:
            pass

    def fake_get(url: str, timeout: float) -> _Response:
        calls.append(url)
        return _Response()

    monkeypatch.setattr(poll.requests, "get", fake_get)
    return calls


def _run(monkeypatch: pytest.MonkeyPatch, config: Config, fetch) -> None:
    monkeypatch.setattr(poll, "load_config", lambda: config)
    monkeypatch.setattr(poll, "fetch_screenshot", fetch)
    poll.run()


def test_heartbeat_after_saved_screenshot(tmp_path, monkeypatch, heartbeats) -> None:
    _run(monkeypatch, _config(tmp_path), lambda url, key: _payload())
    assert heartbeats == [HEARTBEAT_URL]
    assert list((tmp_path / "screenshots").rglob("*.png"))


def test_heartbeat_after_skipped_lock_screen(tmp_path, monkeypatch, heartbeats) -> None:
    _run(monkeypatch, _config(tmp_path), lambda url, key: _payload("Windows Default Lock Screen"))
    assert heartbeats == [HEARTBEAT_URL]


@pytest.mark.parametrize(
    "exc",
    [requests.exceptions.ConnectTimeout("off"), requests.exceptions.HTTPError("500")],
)
def test_no_heartbeat_when_agent_fails(tmp_path, monkeypatch, heartbeats, exc) -> None:
    def fetch(url, key):
        raise exc

    _run(monkeypatch, _config(tmp_path), fetch)
    assert heartbeats == []


def test_no_heartbeat_without_url(tmp_path, monkeypatch, heartbeats) -> None:
    _run(monkeypatch, _config(tmp_path, heartbeat_url=None), lambda url, key: _payload())
    assert heartbeats == []


def test_failed_heartbeat_does_not_fail_poll(tmp_path, monkeypatch, caplog) -> None:
    def broken_get(url, timeout):
        raise requests.exceptions.ConnectionError(f"cannot reach {url}")

    monkeypatch.setattr(poll.requests, "get", broken_get)
    _run(monkeypatch, _config(tmp_path), lambda url, key: _payload())
    assert "Heartbeat failed: ConnectionError" in caplog.text
    assert "token" not in caplog.text
