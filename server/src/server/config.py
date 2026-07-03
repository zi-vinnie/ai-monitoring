import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

_ENV_FILE = find_dotenv()
load_dotenv(_ENV_FILE)

# Relative SCREENSHOT_DIR/DB_PATH are resolved against the .env file's
# directory (not the process's cwd), so where data lands doesn't depend on
# where poll-screenshots happens to be invoked from.
_BASE_DIR = Path(_ENV_FILE).resolve().parent if _ENV_FILE else Path.cwd()


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else _BASE_DIR / path


@dataclass(frozen=True)
class Config:
    agent_url: str
    agent_api_key: str
    screenshot_dir: Path
    db_path: Path
    # Optional LAN gateway/router IP. When set, an unreachable agent is probed
    # against it to tell "Wi-Fi/router down" apart from "machine off".
    router_ip: str | None


def load_config() -> Config:
    return Config(
        agent_url=os.environ["AGENT_URL"],
        agent_api_key=os.environ["AGENT_API_KEY"],
        screenshot_dir=_resolve_path(os.environ.get("SCREENSHOT_DIR", "data/screenshots")),
        db_path=_resolve_path(os.environ.get("DB_PATH", "data/metadata.sqlite3")),
        router_ip=os.environ.get("ROUTER_IP") or None,
    )
