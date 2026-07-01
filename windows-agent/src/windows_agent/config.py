import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    api_key: str


def load_config() -> Config:
    return Config(api_key=os.environ["API_KEY"])
