import uvicorn


def run() -> None:
    uvicorn.run("windows_agent.app:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    run()
