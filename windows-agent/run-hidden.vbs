' Launches the windows-agent with no visible window. Task Scheduler runs this
' via wscript.exe (see windows-agent-task.xml).
'
' Why this exists: a uv virtualenv's pythonw.exe is a trampoline that re-launches
' uv's *console* base python.exe, which then gets its own new console window. So
' pointing the task straight at pythonw.exe still pops a cmd window. Instead we
' launch the console python.exe here with window style 0 (hidden): the hidden
' console is inherited down the trampoline chain, so nothing appears.
'
' Edit both paths below if you cloned somewhere other than
' C:\ProgramData\ai-monitoring.
Dim sh
Set sh = CreateObject("WScript.Shell")
' Working dir = project root so config.py's load_dotenv() finds .env.
sh.CurrentDirectory = "C:\ProgramData\ai-monitoring\windows-agent"
' Args: (command, 0 = hidden window, True = wait so the task stays "Running").
sh.Run """C:\ProgramData\ai-monitoring\windows-agent\.venv\Scripts\python.exe"" -m windows_agent.main", 0, True
