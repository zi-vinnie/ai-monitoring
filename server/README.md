# server

The Ubuntu-side component of the ai-monitoring parental screen-monitoring system.

`poll-screenshots` is a single-shot script, run every 5 minutes by a systemd timer (it does not loop internally). Each run:

1. Sends `GET /screenshot` to the [windows-agent](../windows-agent) (`AGENT_URL`), authenticated with `X-API-Key: AGENT_API_KEY`.
2. Decodes the returned base64 PNG (a capture of whichever monitor holds the focused window).
3. Saves it to `SCREENSHOT_DIR/<YYYY-MM-DD>/<timestamp>_monitor<N>.png`.
4. Inserts a row into the `screenshots` table in SQLite (`DB_PATH`): capture time, monitor index, focused window title, file path.

If the poll fails, it logs the reason and records a row in the `agent_status` table instead of crashing: `unreachable` for a connection error/timeout (machine off, asleep, or agent stopped), `error` for any other HTTP failure. The classifier's daily report counts these as failed polls.

Classification is not done here — the separate [classifier](../classifier) component reads the saved rows later and fills in the `label` column. The exact `/screenshot` response shape is documented in the top-level [CLAUDE.md](../CLAUDE.md#windows-agent-screenshot-contract); if that contract changes, `src/server/fetch.py` and `src/server/poll.py` must change with it.

Image retention (auto-deleting old screenshots while keeping labels) is not yet implemented.

## Setup

Requires Linux, Python 3.12, [uv](https://docs.astral.sh/uv/), and network access to the Windows agent.

```bash
uv sync
cp .env.example .env
```

Edit `.env`:

```
AGENT_URL=http://192.168.1.50:8000   # the Windows agent's address
AGENT_API_KEY=changeme               # must match the agent's API key
SCREENSHOT_DIR=data/screenshots      # where PNGs are saved
DB_PATH=data/metadata.sqlite3        # SQLite metadata db
```

`SCREENSHOT_DIR` and `DB_PATH` are created on first run. Relative paths are resolved against the `.env` file's directory, not the current working directory, so scheduled runs land data in the same place regardless of where they're invoked from.

## Running

```bash
uv run poll-screenshots
```

Fetches one screenshot, saves it, writes one row. Logs go to stderr.

### Scheduling

Scheduled with a **systemd timer** (it's a single-shot script, so any scheduler works — but systemd's `Persistent=true` catches up on runs missed while the server was off, and journald keeps the logs with no redirection or rotation to manage).

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
Description=Run poll-screenshots every 5 minutes

[Timer]
OnCalendar=*:0/5
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl enable --now poll-screenshots.timer
```

Check on it with `systemctl list-timers poll-screenshots.timer` and `journalctl -u poll-screenshots`.

## Database

Schema lives in `src/server/db.py` (this component owns it; the classifier only reads rows and fills `label`).

`screenshots`:

| column        | type    | notes                               |
| ------------- | ------- | ----------------------------------- |
| id            | INTEGER | primary key                         |
| captured_at   | TEXT    | ISO 8601 UTC timestamp from the agent |
| monitor_index | INTEGER | which monitor was captured          |
| window_title  | TEXT    | nullable, focused window title      |
| file_path     | TEXT    | path to the saved PNG               |
| label         | TEXT    | nullable, filled in by `classifier` |

`agent_status` (one row per failed poll):

| column     | type    | notes                                  |
| ---------- | ------- | -------------------------------------- |
| id         | INTEGER | primary key                            |
| checked_at | TEXT    | ISO 8601 UTC timestamp of the attempt  |
| status     | TEXT    | `unreachable` or `error`               |
| detail     | TEXT    | the exception/HTTP error message       |

## Project structure

```
server/
  src/server/
    config.py   # loads env vars from .env, resolves relative paths
    fetch.py    # calls the windows-agent /screenshot endpoint
    db.py       # SQLite schema + insert helpers
    poll.py     # poll-screenshots entry point
```

## Security

- `AGENT_API_KEY` authenticates to the Windows agent — keep `.env` out of version control (already gitignored) and never log its value.
- Intended strictly for authorized monitoring of a household device you own or administer. See the top-level [CLAUDE.md](../CLAUDE.md#security) for the full policy.
