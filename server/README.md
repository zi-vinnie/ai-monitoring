# server

The Ubuntu-side component of the ai-monitoring parental screen-monitoring system.

On a schedule (cron or a systemd timer — this project does not loop internally), `poll-screenshots` calls the [windows-agent](../windows-agent)'s `/screenshot` endpoint once, saves the returned PNG to disk, and records its metadata in SQLite. It does not do any classification itself — that's handled by a separate `classifier` component that reads the saved screenshots later.

## What it does

Each run of `poll-screenshots`:

1. Sends `GET /screenshot` to the Windows agent (`AGENT_URL`), authenticated with `X-API-Key: AGENT_API_KEY`.
2. Decodes the returned base64 PNG (a capture of whichever monitor currently holds the focused window).
3. Saves it to `SCREENSHOT_DIR/<YYYY-MM-DD>/<timestamp>_monitor<N>.png`.
4. Inserts a row into the `screenshots` table in the SQLite database at `DB_PATH`, recording the capture time, monitor index, focused window title, and file path.

See [`windows_agent`'s `/screenshot` contract](../CLAUDE.md#windows-agent-screenshot-contract) for the exact response shape. If that contract ever changes, `server/src/server/fetch.py` and `server/src/server/poll.py` need to change with it.

Image retention (auto-deleting old screenshots while keeping labels) is not yet implemented.

## Requirements

- Linux (developed for Ubuntu)
- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Network access to the Windows agent's `/screenshot` endpoint

## Installation

From the `server/` directory:

```bash
uv sync
```

This creates a `.venv` and installs the project along with its dependencies (`requests`, `python-dotenv`).

## Setup

1. Copy the example env file and fill in your values:

   ```bash
   cp .env.example .env
   ```

2. Edit `.env`:

   ```
   AGENT_URL=http://192.168.1.50:8000   # the Windows agent's address
   AGENT_API_KEY=changeme               # must match the agent's configured API key
   SCREENSHOT_DIR=data/screenshots      # where PNGs are saved
   DB_PATH=data/metadata.sqlite3        # where the SQLite metadata db lives
   ```

   `SCREENSHOT_DIR` and `DB_PATH` are created automatically on first run if they don't exist.

## Running

Run a single poll manually:

```bash
uv run poll-screenshots
```

This fetches one screenshot, saves it, and writes one row to the database. Logs go to stdout.

### Scheduling

`poll-screenshots` is meant to run every 10-15 minutes via cron or a systemd timer — not as a long-lived process.

**Cron example** (every 10 minutes):

```cron
*/10 * * * * cd /path/to/ai-monitoring/server && /path/to/uv run poll-screenshots >> /path/to/logs/poll.log 2>&1
```

**systemd timer example**:

`/etc/systemd/system/poll-screenshots.service`:

```ini
[Unit]
Description=Poll windows-agent for a screenshot

[Service]
Type=oneshot
WorkingDirectory=/path/to/ai-monitoring/server
ExecStart=/path/to/uv run poll-screenshots
```

`/etc/systemd/system/poll-screenshots.timer`:

```ini
[Unit]
Description=Run poll-screenshots every 10 minutes

[Timer]
OnCalendar=*:0/10
Persistent=true

[Install]
WantedBy=timers.target
```

Then enable it:

```bash
sudo systemctl enable --now poll-screenshots.timer
```

## Data layout

```
data/
  screenshots/
    2026-07-01/
      20260701T132000Z_monitor1.png
  metadata.sqlite3
```

The `screenshots` table (`server/src/server/db.py`):

| column         | type    | notes                              |
|----------------|---------|-------------------------------------|
| id             | INTEGER | primary key                        |
| captured_at    | TEXT    | ISO 8601 timestamp from the agent  |
| monitor_index  | INTEGER | which monitor was captured         |
| window_title   | TEXT    | nullable, focused window title     |
| file_path      | TEXT    | path to the saved PNG              |
| label          | TEXT    | nullable, filled in by `classifier`|

## Project structure

```
server/
  src/server/
    config.py   # loads AGENT_URL, AGENT_API_KEY, SCREENSHOT_DIR, DB_PATH from .env
    fetch.py    # calls the windows-agent /screenshot endpoint
    db.py       # SQLite schema + insert helper
    poll.py     # poll-screenshots entry point, ties the above together
  .env.example
  pyproject.toml
```

## Security

- `AGENT_API_KEY` authenticates to the Windows agent — keep `.env` out of version control (already gitignored) and never log its value.
- This tool is intended strictly for authorized monitoring of a household device you own or administer, with the awareness of the device's user where required. See the top-level [CLAUDE.md](../CLAUDE.md#security) for the full policy.
