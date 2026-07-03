' Auto-updates (git pull + uv sync) and then launches the windows-agent with no
' visible window. Task Scheduler runs this via wscript.exe (see
' windows-agent-task.xml).
'
' The actual work lives in update-and-run.cmd; this wrapper exists only to run
' it hidden. Why hidden matters: a uv venv's console python.exe -- plus git and
' uv themselves -- would each flash a console window. Launching the .cmd with
' window style 0 (hidden) means that hidden console is inherited by every child
' process it spawns, so nothing ever appears on screen.
'
' Edit the paths below if you cloned somewhere other than
' C:\ProgramData\ai-monitoring.
Dim sh
Set sh = CreateObject("WScript.Shell")
' Working dir = project root so config.py's load_dotenv() finds .env.
sh.CurrentDirectory = "C:\ProgramData\ai-monitoring\windows-agent"
' Args: (command, 0 = hidden window, True = wait so the task stays "Running"
' for the life of the agent). cmd runs the batch synchronously, so it doesn't
' return until the agent process exits.
sh.Run "cmd /c ""C:\ProgramData\ai-monitoring\windows-agent\update-and-run.cmd""", 0, True
