@echo off
rem Auto-update, then launch the windows-agent. Invoked hidden by run-hidden.vbs
rem at logon (see windows-agent-task.xml). Runs from the windows-agent directory.
rem
rem Order matters: git pull + uv sync run BEFORE the agent starts. That's safe
rem precisely because, at logon, no previous agent is running (the task is
rem "run only when the user is logged on", so the prior instance was terminated
rem at logoff) -- so nothing has the .venv's python.exe / .pyd files locked and
rem uv sync can replace them. Never run this while an agent instance is live.
rem
rem git pull / uv sync failures (e.g. offline, or a diverged branch) are
rem non-fatal: we note them and start the agent anyway, so a network hiccup can
rem never leave the machine unmonitored. New deps that a failed sync missed just
rem stay absent until the next successful logon (imports for them are guarded).

setlocal
cd /d "%~dp0"

rem Build/reuse the venv against the machine-wide system Python (all users),
rem never a per-user managed Python under one account's profile. A per-user
rem interpreter is unreadable by any other account, so a venv pointing at it
rem breaks the moment a different user runs the agent ("Access is denied" /
rem "uv trampoline failed to spawn Python"). only-system keeps the interpreter
rem in an all-users location so the agent works regardless of who is logged on.
rem Requires an all-users Python 3.12 to be installed (e.g. C:\Program Files\
rem Python312); see windows-agent/README.md.
set "UV_PYTHON_PREFERENCE=only-system"

rem Single log, truncated each logon so it can't grow without bound.
set "LOG=%~dp0update.log"
echo [%date% %time%] logon update starting> "%LOG%"

rem Repo root is the parent of windows-agent (monorepo layout). --ff-only keeps
rem this a no-op-or-fast-forward: it never creates merge commits or conflicts.
git -C "%~dp0.." pull --ff-only>> "%LOG%" 2>&1
if errorlevel 1 echo [%date% %time%] git pull failed or skipped, continuing>> "%LOG%"

uv sync>> "%LOG%" 2>&1
if errorlevel 1 echo [%date% %time%] uv sync failed, starting with existing venv>> "%LOG%"

echo [%date% %time%] starting agent>> "%LOG%"
"%~dp0.venv\Scripts\python.exe" -m windows_agent.main>> "%LOG%" 2>&1
