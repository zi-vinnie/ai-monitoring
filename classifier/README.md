# classifier

The daily analysis + reporting component of the ai-monitoring parental screen-monitoring system.

It has two scheduled, single-shot entry points that share the SQLite database the [server](../server) writes:

1. **`classify-screenshots`** — labels the day's screenshots with a local [Ollama](https://ollama.com) vision model.
2. **`send-report`** — aggregates the day's labels into time-per-category, renders a chart, and emails a summary.

Neither loops internally; both are meant to run once a day by a systemd timer (classify first, then report).

## Categories

Every screenshot is labelled with exactly one of:

`productive` · `gaming` · `video_entertainment` · `social_media` · `browsing` · `unknown`

Because the agent only ever captures the monitor holding the focused window, there's one image in and one label out — no cross-monitor reconciliation.

## How `classify-screenshots` works

1. Reads the day's `screenshots` rows where `label IS NULL` from the shared DB.
2. For each, base64-encodes the PNG (downscaled to `OLLAMA_IMAGE_MAX_EDGE`) and sends it to Ollama's `/api/generate` with the focused window title as a hint and a structured-output `format`, at `temperature 0`. The JSON schema asks for a one-sentence `screen_content` description *before* a `label` constrained to the six categories — describing the screen first is a cheap reasoning step that helps the small vision model pick the right label.
3. Writes the returned label back to the row.

Per-image failures (Ollama down, model missing, timeout, a deleted image file, an unrecognisable response) are logged and skipped — the row stays unlabelled so a later run retries it, rather than aborting the batch.

## How `send-report` works

1. Reads the day's labelled rows and counts failed polls (from `agent_status`) for a "monitoring gaps" note.
2. Converts label counts to minutes (`count × POLL_INTERVAL_MINUTES` — each screenshot stands in for one poll interval of that activity).
3. Renders a horizontal bar chart (PNG, via matplotlib) of time-per-category.
4. Emails a plain-text + HTML summary with the chart embedded inline (and attached) to every address in `EMAIL_TO`, over SMTP.

If nothing was labelled for the day, it sends a short "no activity recorded" notice instead (noting whether every poll failed).

> Email was chosen over WhatsApp deliberately: no 24-hour session window or template pre-approval, and the chart image is sent as bytes directly (SMTP multipart) with no need to host it at a public URL.

## Requirements

- Linux (developed for Ubuntu)
- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- A running Ollama with a pulled vision model (for `classify-screenshots`)
- An SMTP account to send from (for `send-report`)
- Read/write access to the `server` component's SQLite database

## Installation

From the `classifier/` directory:

```bash
uv sync
```

### Ollama

Install Ollama and pull a vision model (the default is `minicpm-v4.6`):

```bash
# https://ollama.com/download
ollama pull minicpm-v4.6
```

Any vision model Ollama supports works — set `OLLAMA_MODEL` to it. Smaller models (e.g. `moondream`) are faster but less accurate; larger ones are slower on CPU (raise `OLLAMA_TIMEOUT`).

## Setup

Copy the example env file and fill it in:

```bash
cp .env.example .env
```

| variable | purpose |
| --- | --- |
| `DB_PATH` | path to the server's SQLite DB (default points at `../server/data/metadata.sqlite3`) |
| `OLLAMA_URL` | Ollama base URL (default `http://localhost:11434`) |
| `OLLAMA_MODEL` | vision model name (default `minicpm-v4.6`) |
| `OLLAMA_TIMEOUT` | per-image request timeout, seconds (default `120`) |
| `OLLAMA_IMAGE_MAX_EDGE` | downscale each screenshot to this longest edge in px before sending, so large captures fit a small model's context window (default `1280`; `0` = full size) |
| `POLL_INTERVAL_MINUTES` | minutes each screenshot represents — set to the server's poll interval (default `10`) |
| `REPORT_TZ` | IANA timezone defining "a day"; blank = server local time |
| `SMTP_HOST` / `SMTP_PORT` | SMTP server (default port `587`) |
| `SMTP_STARTTLS` | `true` (default) to upgrade the port-587 connection to TLS with STARTTLS |
| `SMTP_SSL` | `true` for implicit TLS from the first byte (typically port `465`); default `false`. When set, STARTTLS is skipped |
| `SMTP_USER` / `SMTP_PASSWORD` | SMTP credentials (omit for an unauthenticated relay) |
| `EMAIL_FROM` | From address |
| `EMAIL_TO` | comma-separated recipient list |

Relative `DB_PATH` resolves against the `.env` file's directory, so the job can be invoked from anywhere.

### Setting up email (SMTP)

SMTP is the protocol mail apps use to hand a message to a mail server for delivery — `send-report` acts like a mail app: it connects to your provider's SMTP server, logs in, and hands over the report. You don't run a mail server yourself; you just need an account to send *from* (Gmail works well).

**Gmail setup** (5 minutes):

1. Gmail blocks your normal password for SMTP, so you need an **app password**. That requires 2-Step Verification: [myaccount.google.com/security](https://myaccount.google.com/security) → turn on **2-Step Verification** if it isn't already.
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), enter a name like `ai-monitoring`, and click **Create**. Google shows a 16-character password **once** — copy it.
3. In `.env`, set:
   - `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_STARTTLS=true` (already the example defaults)
   - `SMTP_USER` and `EMAIL_FROM` to your Gmail address
   - `SMTP_PASSWORD` to the app password (spaces are fine)
   - `EMAIL_TO` to the recipient(s), comma-separated
4. Test it: `uv run send-report --date yesterday`. The report (or a "no activity recorded" notice) should arrive within seconds; errors print to the terminal — `535` means the username/app password is wrong.

Any other provider works the same way: its SMTP host/port and a login. Port 587 uses STARTTLS (the default here); if a provider only offers port 465, set `SMTP_PORT=465` and `SMTP_SSL=true`.

## Running

```bash
uv run classify-screenshots                     # label today's screenshots
uv run send-report                              # email today's summary

uv run classify-screenshots --date yesterday    # the previous day (for morning schedules)
uv run send-report --date 2026-07-02            # or an explicit day
```

`--date` accepts `YYYY-MM-DD`, `today`, or `yesterday`, interpreted in `REPORT_TZ`.

### Scheduling

Run once daily, classify before report. The intended schedule covers the **previous day**: classify in the small hours (when the machine is idle and the day's screenshots are complete), then send the report at breakfast time — both with `--date yesterday`.

Scheduled with **systemd timers**, like the server's `poll-screenshots`. `Persistent=true` catches up on runs missed while the server was off — without it, a server that's asleep at 09:00 simply never sends that day's report — and logs land in journald.

`/etc/systemd/system/classify-screenshots.service`:

```ini
[Unit]
Description=Label yesterday's screenshots with the local Ollama vision model

[Service]
Type=oneshot
WorkingDirectory=/path/to/ai-monitoring/classifier
ExecStart=/path/to/uv run classify-screenshots --date yesterday
```

`/etc/systemd/system/classify-screenshots.timer`:

```ini
[Unit]
Description=Run classify-screenshots daily at 03:00

[Timer]
OnCalendar=03:00
Persistent=true

[Install]
WantedBy=timers.target
```

`/etc/systemd/system/send-report.service`:

```ini
[Unit]
Description=Email yesterday's screen-time summary
# If a catch-up run fires both jobs at once (e.g. at boot), classify goes first.
After=classify-screenshots.service

[Service]
Type=oneshot
WorkingDirectory=/path/to/ai-monitoring/classifier
ExecStart=/path/to/uv run send-report --date yesterday
```

`/etc/systemd/system/send-report.timer`:

```ini
[Unit]
Description=Run send-report daily at 09:00

[Timer]
OnCalendar=09:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl enable --now classify-screenshots.timer send-report.timer
```

(`/path/to/uv` = the output of `command -v uv`. `OnCalendar` uses the server's local clock; the *day boundaries* come from `REPORT_TZ`.)

Check the schedule with `systemctl list-timers`, and logs with `journalctl -u classify-screenshots -u send-report`. The 03:00→09:00 gap doubles as a retry window: if Ollama was down at 3am, rows stay unlabelled and a manual `uv run classify-screenshots --date yesterday` (or `systemctl start classify-screenshots.service`) before 9am fills them in — the report only counts labels present when it runs.

## Project structure

```
classifier/
  src/classifier/
    config.py         # loads DB_PATH, Ollama, SMTP, and reporting env vars
    timeframe.py      # target-day parsing + local-day -> UTC bounds
    categories.py     # the six categories, the prompt, structured-output schema, label parsing
    db.py             # reads unlabeled rows / writes labels against the shared DB
    ollama_client.py  # calls Ollama's /api/generate with the image
    classify.py       # classify-screenshots entry point
    aggregate.py      # labels -> time-per-category (pure)
    chart.py          # renders the time-per-category bar chart PNG
    emailer.py        # builds + sends the multipart email
    report.py         # send-report entry point
  tests/
  .env.example
  pyproject.toml
```

## Security & privacy

- `.env` holds SMTP credentials and is gitignored — never commit it or log its values.
- Reports summarise a monitored household device for authorized parental monitoring only; see the top-level [CLAUDE.md](../CLAUDE.md#security) for the full policy.
- The report emails per-category *time totals*, not the screenshots themselves; image retention/deletion stays the server's concern.
