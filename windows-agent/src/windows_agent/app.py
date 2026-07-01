import secrets
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException

from windows_agent.capture import capture_active_monitor
from windows_agent.config import load_config

app = FastAPI()


def require_api_key(x_api_key: str = Header(...)) -> None:
    config = load_config()
    if not secrets.compare_digest(x_api_key, config.api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/screenshot", dependencies=[Depends(require_api_key)])
def get_screenshot() -> dict:
    result = capture_active_monitor()
    return {"captured_at": datetime.now(timezone.utc).isoformat(), **result}
