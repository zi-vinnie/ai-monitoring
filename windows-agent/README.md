# windows-agent

The Windows-side component of the ai-monitoring parental screen-monitoring system.

A FastAPI service on the monitored machine exposing one API-key-protected endpoint, `GET /screenshot`, which captures **only the monitor currently holding the focused window** and returns it as base64 PNG. The [server](../server) component polls it every 10–15 minutes.

## How it works

On each request (authenticated via `X-API-Key`, checked with `secrets.compare_digest`):

1. Finds the foreground window and its monitor (`pywin32`), matching it to an `mss` monitor index by greatest rect overlap (robust to DPI-scaling offsets). Falls back to monitor 1 if no window is focused.
2. Captures that monitor with `mss` (GDI). If the frame comes back black — which happens for **exclusive-fullscreen games** (Rocket League etc.) because they bypass the desktop compositor — it re-captures via the **Desktop Duplication API** (`dxcam`), which reads the GPU output directly. This path is fallback-only: normal captures never hit it, and any `dxcam` failure keeps the original frame.
3. Returns:

   ```json
   {
     "captured_at": "2026-07-01T13:20:00+00:00",
     "monitor_index": 1,
     "window_title": "Instagram - Google Chrome",
     "png_base64": "..."
   }
   ```

   `window_title` is `null` if there's no focused window.

## Setup

Requires Windows (the win32/dxcam code is import-guarded, so the project still installs elsewhere, but `/screenshot` only works on Windows), Python 3.12, and [uv](https://docs.astral.sh/uv/).

```powershell
uv sync
copy .env.example .env
```

Set `API_KEY` in `.env` to a long random value (`python -c "import secrets; print(secrets.token_hex(32))"`) and use the same value for `AGENT_API_KEY` in the server's `.env`. Never commit or log it.

The agent binds to `0.0.0.0:8000` so the server can reach it over the LAN. Scope inbound access to the server's IP:

```powershell
New-NetFirewallRule -DisplayName "windows-agent screenshot" `
  -Direction Inbound -Protocol TCP -LocalPort 8000 `
  -RemoteAddress <server-lan-ip> -Action Allow
```

## Running

```powershell
uv run windows-agent
```

Test from the machine itself:

```powershell
curl.exe -s -H "X-API-Key: changeme" http://127.0.0.1:8000/screenshot -o shot.json
uv run python -c "import json,base64; d=json.load(open('shot.json')); b=base64.b64decode(d['png_base64']); open('shot.png','wb').write(b); print('bytes:', len(b), 'monitor:', d['monitor_index'], 'title:', d['window_title'])"
start shot.png
```

(Decode with Python rather than PowerShell's `ConvertFrom-Json`, which can truncate the long base64 string.)

Run tests with `uv run pytest`.

## Deploying: hidden, auto-starting, auto-updating

The agent should start at logon and run with no visible window. **It must run in the logged-on user's interactive session** — a session-0 service (NSSM, or Task Scheduler's "Run whether user is logged on or not") has no visible desktop, so capture returns black frames. Use the provided Task Scheduler task instead, from an elevated PowerShell:

```powershell
schtasks /Create /TN "windows-agent" /XML "C:\ProgramData\ai-monitoring\windows-agent\windows-agent-task.xml" /F
```

The task is preconfigured: logon trigger, runs as the logged-on user, hidden, no time limit, restart-on-failure. It runs `wscript.exe run-hidden.vbs`, which launches `update-and-run.cmd` with a hidden console inherited by all children (pointing the task straight at `pythonw.exe` doesn't work — a uv venv's `pythonw.exe` re-launches the console base `python.exe`, which pops a window). If you cloned somewhere other than `C:\ProgramData\ai-monitoring`, edit the paths in both `run-hidden.vbs` and the XML's `<WorkingDirectory>`.

`update-and-run.cmd` self-updates before starting the agent: `git pull --ff-only`, then `uv sync`, then launch. Both steps are best-effort — if offline or diverged, it logs and starts anyway, so a bad pull never leaves the machine unmonitored. Output goes to `update.log` (truncated each logon). This is safe at logon because the previous instance died at logoff, so nothing locks the `.venv`; to update a *running* agent mid-session, restart the task (Task Scheduler → **End**, then **Run**).

Prerequisites: `git` and `uv` on the user's `PATH`, and `git pull` must work non-interactively (public repo or cached credentials). **Security implication: anyone who can push to this repo gets code execution on the monitored machine at its next logon.**

To verify: run the task (or log off and on), hit `/screenshot` from the server, and check `update.log`.

## Security

- Never remove or weaken the API-key check, and never log or print the key.
- Traffic is plain HTTP — the key and screenshots travel in cleartext on the LAN. On an untrusted network, use a VPN/overlay (Tailscale/WireGuard) or add TLS.
- Keep the firewall rule (above) so the key isn't the only protection.
- Intended strictly for authorized parental monitoring of a household device. Do not extend it toward covert surveillance or stalkerware features — see the top-level [CLAUDE.md](../CLAUDE.md#security) for the full policy.

## Project structure

```
windows-agent/
  src/windows_agent/
    config.py          # loads API_KEY from .env
    active_monitor.py  # win32 foreground window/monitor detection, DPI awareness
    capture.py         # mss capture, monitor matching, black-frame detection
    capture_dxgi.py    # Desktop Duplication fallback for fullscreen games
    app.py             # FastAPI app, /screenshot endpoint, API key check
    main.py            # uvicorn entry point (windows-agent script)
  tests/               # pure-function tests (monitor matching, black detection)
  run-hidden.vbs       # launches update-and-run.cmd with no visible window
  update-and-run.cmd   # git pull + uv sync + start agent, logs to update.log
  windows-agent-task.xml  # importable Task Scheduler task (logon, hidden)
```
