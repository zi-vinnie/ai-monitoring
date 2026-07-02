# windows-agent

The Windows-side component of the ai-monitoring parental screen-monitoring system.

It runs as a background service on the monitored Windows machine and exposes a single API-key-protected endpoint, `/screenshot`, that captures **only the monitor currently holding the focused window** and returns it as a base64 PNG. The [server](../server) component polls this endpoint every 10-15 minutes.

## What it does

On each `GET /screenshot` request (authenticated via `X-API-Key`):

1. Finds the foreground window and the monitor it's on (`win32gui.GetForegroundWindow` + `win32api.MonitorFromWindow`).
2. Matches that monitor to its index in `mss`'s monitor list.
3. Captures just that monitor and encodes it as PNG/base64.
4. Returns:

   ```json
   {
     "captured_at": "2026-07-01T13:20:00+00:00",
     "monitor_index": 1,
     "window_title": "Instagram - Google Chrome",
     "png_base64": "..."
   }
   ```

   `window_title` is `null` if there's no focused window. If there's no focused window, monitor 1 is captured as a fallback.

No cross-monitor stitching or reconciliation is done — since only the focused monitor is captured, there's exactly one image and one label per capture.

## Requirements

- Windows (the active-window/monitor detection uses `pywin32` and only works there — the project still installs and resolves on other platforms, but calling `/screenshot` off-Windows will raise)
- Python 3.12
- [uv](https://docs.astral.sh/uv/)

## Installation

From the `windows-agent/` directory:

```powershell
uv sync
```

This creates a `.venv` and installs `fastapi`, `mss`, `uvicorn`, `python-dotenv`, and (on Windows) `pywin32`.

## Setup

1. Copy the example env file and set a real key:

   ```powershell
   copy .env.example .env
   ```

2. Edit `.env`:

   ```
   API_KEY=changeme
   ```

   Use a long, random value (e.g. `python -c "import secrets; print(secrets.token_hex(32))"`) and use the same value for `AGENT_API_KEY` in the server's `.env`. Never commit `.env` or log this key — `.env` is already gitignored.

3. The agent listens on all interfaces at port 8000 (`0.0.0.0:8000`) so the server can reach it over the LAN. Restrict who can actually connect with a Windows Firewall inbound rule scoped to the server's IP:

   ```powershell
   New-NetFirewallRule -DisplayName "windows-agent screenshot" `
     -Direction Inbound -Protocol TCP -LocalPort 8000 `
     -RemoteAddress <server-lan-ip> -Action Allow
   ```

   Without a rule like this, any device on the LAN that has (or guesses) the API key can reach the endpoint.

## Running

```powershell
uv run windows-agent
```

This starts the FastAPI app under uvicorn on `0.0.0.0:8000`. Test it from the machine itself:

```powershell
curl.exe -H "X-API-Key: changeme" http://127.0.0.1:8000/screenshot
```

To verify the returned image is a real, complete screenshot (rather than eyeballing the JSON), decode it with Python — avoid Windows PowerShell's `ConvertFrom-Json`, which can truncate the long base64 string and produce a "corrupted" PNG:

```powershell
curl.exe -s -H "X-API-Key: changeme" http://127.0.0.1:8000/screenshot -o shot.json
uv run python -c "import json,base64; d=json.load(open('shot.json')); b=base64.b64decode(d['png_base64']); open('shot.png','wb').write(b); print('bytes:', len(b), 'monitor:', d['monitor_index'], 'title:', d['window_title'])"
start shot.png
```

### Running hidden / as a background service

The agent is meant to run hidden on the monitored machine rather than as a visible console window, and to start automatically so the server's polling doesn't silently fail after a reboot.

**Important — it must run in the logged-on user's interactive session.** Screen capture only works from an interactive desktop. A background *service* (NSSM, or Task Scheduler's "Run whether user is logged on or not") runs in **session 0**, which has no visible desktop, so `mss` there captures **black frames** or fails outright. Don't use NSSM/session-0 for this. Instead run it via Task Scheduler triggered at the monitored user's logon, in their session — capturing their screen while they use it (there's nothing meaningful to capture when they're logged out).

**Import the provided task** ([`windows-agent-task.xml`](./windows-agent-task.xml)) — it's preconfigured for all of the above (logon trigger, runs as the logged-on user, hidden, no console window, no execution time limit, restart-on-failure). From an elevated PowerShell:

```powershell
schtasks /Create /TN "windows-agent" /XML "C:\ProgramData\ai-monitoring\windows-agent\windows-agent-task.xml" /F
```

Or in the Task Scheduler GUI: **Action → Import Task…** and select the XML.

The task's Action uses `.venv\Scripts\pythonw.exe -m windows_agent.main` (`pythonw`, so no console window ever appears) with the **working directory set to the project folder** — this matters because `config.py` calls `load_dotenv()`, which looks for `.env` relative to the working directory. If you cloned somewhere other than `C:\ProgramData\ai-monitoring`, edit the three paths in the XML (`<Command>`, `<WorkingDirectory>`) before importing.

To verify: after importing, log off and back on (or right-click the task → **Run**), then hit `/screenshot` from the server — you should get JSON back with no visible window on the monitored machine.

## Security

- `/screenshot` is API-key protected via the `X-API-Key` header, compared with `secrets.compare_digest` to avoid timing attacks. Never remove or weaken this check, and never log or print the API key.
- Traffic between the server and this agent is plain HTTP — the API key and screenshot bytes are sent in cleartext. On an untrusted or shared network, put this behind a VPN/overlay network (e.g. Tailscale/WireGuard) or add TLS rather than exposing it over the open LAN.
- Scope inbound access to the server's IP with a firewall rule (see Setup above) so the API key isn't the only thing standing between the LAN and this endpoint.
- This tool is intended strictly for authorized parental monitoring of a household device. Do not extend it toward covert surveillance of adults without consent, or add remote-install/hidden-persistence/keylogging features that would turn it into general-purpose stalkerware — see the top-level [CLAUDE.md](../CLAUDE.md#security) for the full policy.

## Project structure

```
windows-agent/
  src/windows_agent/
    config.py         # loads API_KEY from .env
    active_monitor.py # win32 foreground window + monitor detection
    capture.py         # matches win32 monitor rect to an mss monitor index, captures PNG
    app.py            # FastAPI app, /screenshot endpoint, API key check
    main.py           # uvicorn entry point (windows-agent script)
  .env.example
  pyproject.toml
```
