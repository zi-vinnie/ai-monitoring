# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A parental screen-monitoring system with three components, laid out as a monorepo (one directory per component — layout not yet created):

1. **Windows agent** (`windows-agent/`) — Python + FastAPI + `mss`, built with `uv` (src layout, `pyproject.toml` + `uv.lock`). Runs as a hidden background service on the monitored Windows machine. Exposes a local `/screenshot` endpoint, protected by an API key (`X-API-Key` header), that captures **only the monitor currently holding the focused window** and returns it as a single base64 PNG. Active-window/monitor detection uses `pywin32` (`GetForegroundWindow` + `MonitorFromWindow`), declared with an `; sys_platform == 'win32'` marker in `pyproject.toml` so the project still resolves on non-Windows dev machines — the win32-specific code in `windows_agent/active_monitor.py` is import-guarded and only raises if actually called off-Windows. `windows_agent/capture.py` matches the win32 monitor rect to mss's monitor index via `match_monitor_index` (a pure function, unit-testable without a real display or Windows). Entry point: `uv run windows-agent`.
2. **Ubuntu server** (`server/`) — plain Python, no n8n, built with `uv` (src layout). A `poll-screenshots` script (invoked on a schedule via cron or a systemd timer, not an internal loop) calls the Windows agent's `/screenshot` endpoint every 10–15 minutes, saves the single PNG under `data/screenshots/<date>/`, and records metadata (timestamp, monitor index, focused window title, file path, label) in SQLite (`server/src/server/db.py`). Config is via env vars (`AGENT_URL`, `AGENT_API_KEY`, `SCREENSHOT_DIR`, `DB_PATH`) loaded from `.env` — see `server/.env.example`. Auto-deletion of images after a few days (retaining labels longer) is not yet implemented.
3. **Local AI classifier** (`classifier/`) — a daily job running a local vision model (Ollama or similar) over the day's screenshots. Labels each into one of: `schoolwork`, `gaming`, `video_entertainment`, `social_media`, `browsing_other`, `idle_locked`. Since only the focused monitor is captured, there's no cross-monitor reconciliation/priority step needed — one image in, one label out.
4. **WhatsApp summary** — plain Python (Twilio's Python SDK), no n8n. Aggregates labels into time-per-category and sends a daily summary via WhatsApp. Not yet implemented — likely lives alongside the classifier or as its own script in `server/`.

n8n was considered for the server-side polling/aggregation/notification steps but rejected in favor of plain Python: simpler to test, version-control, and reason about for logic this straightforward. Capturing all monitors and stitching/reconciling them was also considered and rejected in favor of active-window detection — it's simpler (no reconciliation logic), cheaper (half the storage and classification calls with two monitors), and more accurate (captures literal focus instead of inferring which monitor's activity "wins").

### Windows agent `/screenshot` contract

```json
{
  "captured_at": "2026-07-01T13:20:00+00:00",
  "monitor_index": 1,
  "window_title": "Instagram - Google Chrome",
  "png_base64": "..."
}
```
Request: `GET /screenshot` with header `X-API-Key: <key>`. `window_title` is nullable (e.g. no focused window). If this contract changes, update both `windows_agent/app.py`/`windows_agent/capture.py` and `server/src/server/fetch.py`/`server/src/server/poll.py` together.

## Security

- The Windows agent's `/screenshot` endpoint is API-key protected — never remove or weaken this auth, and never log or print the API key.
- This system captures screenshots of a monitored machine and is intended strictly for authorized parental monitoring of a household device. Do not extend it toward covert surveillance of adults without consent, or add features (remote install, hidden persistence beyond the stated hidden-service design, keylogging, etc.) that would turn it into general-purpose stalkerware.
- Image retention/deletion windows (a few days for images, longer for labels) are a deliberate privacy tradeoff — don't casually extend retention when touching the cleanup job.
