import base64
import sqlite3
from pathlib import Path

import pytest
import requests

from server import poll
from server.config import Config

PUSH_TOKEN = "SECRET-PUSH-TOKEN-123"
HEARTBEAT_URL = f"http://kuma.test/api/push/{PUSH_TOKEN}?status=up"


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


class _Response:
    def __init__(self, status_code: int = 200) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} for url: {HEARTBEAT_URL}")


@pytest.fixture
def heartbeats(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []

    def fake_get(url: str, timeout: float) -> _Response:
        calls.append(url)
        return _Response()

    monkeypatch.setattr(poll.requests, "get", fake_get)
    return calls


def _run(monkeypatch: pytest.MonkeyPatch, config: Config, fetch) -> None:
    monkeypatch.setattr(poll, "load_config", lambda: config)
    monkeypatch.setattr(poll, "fetch_screenshot", fetch)
    poll.run()


def _screenshot_rows(config: Config) -> int:
    conn = sqlite3.connect(config.db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM screenshots").fetchone()[0]
    finally:
        conn.close()


def _assert_token_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    assert PUSH_TOKEN not in caplog.text
    assert HEARTBEAT_URL not in caplog.text


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


def _connection_error(url, timeout):
    raise requests.exceptions.ConnectionError(f"cannot reach {url}")


def _not_found(url, timeout):
    # Uptime Kuma answers 404 for an unknown token or a paused monitor.
    return _Response(404)


def _bad_url(url, timeout):
    # A malformed URL can raise errors outside RequestException.
    raise ValueError(f"bad url {url}")


@pytest.mark.parametrize("get", [_connection_error, _not_found, _bad_url])
def test_failed_heartbeat_does_not_fail_poll(tmp_path, monkeypatch, caplog, get) -> None:
    monkeypatch.setattr(poll.requests, "get", get)
    config = _config(tmp_path)
    _run(monkeypatch, config, lambda url, key: _payload())
    assert list((tmp_path / "screenshots").rglob("*.png"))
    assert _screenshot_rows(config) == 1
    assert "Heartbeat failed:" in caplog.text
    _assert_token_not_logged(caplog)


def test_failed_heartbeat_on_lock_screen_does_not_fail_poll(tmp_path, monkeypatch, caplog) -> None:
    monkeypatch.setattr(poll.requests, "get", _connection_error)
    _run(monkeypatch, _config(tmp_path), lambda url, key: _payload("Windows Default Lock Screen"))
    assert "Heartbeat failed: ConnectionError" in caplog.text
    _assert_token_not_logged(caplog)
