import uvicorn

from windows_agent.app import app


def run() -> None:
    # Pass the app object, not an import string. With an import string uvicorn
    # can run a supervisor that spawns a worker subprocess; launched under
    # pythonw.exe (no console) that console-subsystem child gets its own visible
    # window. The app object forces a single in-process server, so no window.
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run()
