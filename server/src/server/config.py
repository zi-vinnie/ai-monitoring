import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    agent_url: str
    agent_api_key: str
    screenshot_dir: Path
    db_path: Path


def load_config() -> Config:
    return Config(
        agent_url=os.environ["AGENT_URL"],
        agent_api_key=os.environ["AGENT_API_KEY"],
        screenshot_dir=Path(os.environ.get("SCREENSHOT_DIR", "data/screenshots")),
        db_path=Path(os.environ.get("DB_PATH", "data/metadata.sqlite3")),
    )
