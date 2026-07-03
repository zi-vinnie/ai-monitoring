# classifier

The daily analysis + reporting component of the ai-monitoring parental screen-monitoring system.

It has two scheduled, single-shot entry points that share the SQLite database the [server](../server) writes:

1. **`classify-screenshots`** — labels the day's screenshots with a local [Ollama](https://ollama.com) vision model.
2. **`send-report`** — aggregates the day's labels into time-per-category, renders a chart, and emails a summary.

Neither loops internally; both are meant to run once a day from cron or a systemd timer (classify first, then report).

## Categories

Every screenshot is labelled with exactly one of:

`schoolwork` · `gaming` · `video_entertainment` · `social_media` · `browsing_other` · `idle_locked`

Because the agent only ever captures the monitor holding the focused window, there's one image in and one label out — no cross-monitor reconciliation.

## How `classify-screenshots` works

1. Reads the day's `screenshots` rows where `label IS NULL` from the shared DB.
2. For each, base64-encodes the PNG and sends it to Ollama's `/api/generate` with the focused window title as a hint and a structured-output `format` (a JSON schema whose `label` is constrained to the six categories), at `temperature 0`.
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

Install Ollama and pull a vision model (the default is `llama3.2-vision`):

```bash
# https://ollama.com/download
ollama pull llama3.2-vision
```

Any vision model Ollama supports works — set `OLLAMA_MODEL` to it. Smaller models (e.g. `llava`) are faster but less accurate; larger ones are slower on CPU (raise `OLLAMA_TIMEOUT`).

## Setup

Copy the example env file and fill it in:

```bash
cp .env.example .env
```

| variable | purpose |
| --- | --- |
| `DB_PATH` | path to the server's SQLite DB (default points at `../server/data/metadata.sqlite3`) |
| `OLLAMA_URL` | Ollama base URL (default `http://localhost:11434`) |
| `OLLAMA_MODEL` | vision model name (default `llama3.2-vision`) |
| `OLLAMA_TIMEOUT` | per-image request timeout, seconds (default `120`) |
| `POLL_INTERVAL_MINUTES` | minutes each screenshot represents — set to the server's poll interval (default `10`) |
| `REPORT_TZ` | IANA timezone defining "a day"; blank = server local time |
| `SMTP_HOST` / `SMTP_PORT` | SMTP server (default port `587`) |
| `SMTP_STARTTLS` | `true` (default) to upgrade with STARTTLS |
| `SMTP_USER` / `SMTP_PASSWORD` | SMTP credentials (omit for an unauthenticated relay) |
| `EMAIL_FROM` | From address |
| `EMAIL_TO` | comma-separated recipient list |

Relative `DB_PATH` resolves against the `.env` file's directory, so the job can be invoked from anywhere.

## Running

```bash
uv run classify-screenshots          # label today's screenshots
uv run send-report                   # email today's summary

uv run classify-screenshots --date 2026-07-02   # a specific day
uv run send-report --date 2026-07-02
```

### Scheduling

Run once daily, classify before report. A common pattern is to summarise *yesterday* early each morning (pass `--date` for the previous day), or summarise *today* late in the evening.

**Cron example** (classify at 23:30, report at 23:45, for the current day):

```cron
30 23 * * * cd /path/to/ai-monitoring/classifier && /path/to/uv run classify-screenshots >> /path/to/logs/classify.log 2>&1
45 23 * * * cd /path/to/ai-monitoring/classifier && /path/to/uv run send-report      >> /path/to/logs/report.log   2>&1
```

For systemd timers, follow the same shape as the server's `poll-screenshots` units (`Type=oneshot`, a `.timer` with `OnCalendar=`).

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
