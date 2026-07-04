import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

_ENV_FILE = find_dotenv()
load_dotenv(_ENV_FILE)

# A relative DB_PATH is resolved against the .env file's directory (not the
# process cwd), so it doesn't matter where the scheduled job is invoked from.
# The default points at the sibling `server` component's database.
_BASE_DIR = Path(_ENV_FILE).resolve().parent if _ENV_FILE else Path.cwd()
_DEFAULT_DB = "../server/data/metadata.sqlite3"


def _resolve_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else _BASE_DIR / path


def _db_path() -> Path:
    return _resolve_path(os.environ.get("DB_PATH", _DEFAULT_DB))


def _split_recipients(value: str) -> list[str]:
    return [addr.strip() for addr in value.split(",") if addr.strip()]


@dataclass(frozen=True)
class ClassifyConfig:
    db_path: Path
    ollama_url: str
    ollama_model: str
    request_timeout: float
    image_max_edge: int
    report_tz: str | None


@dataclass(frozen=True)
class ReportConfig:
    db_path: Path
    poll_interval_minutes: float
    report_tz: str | None
    smtp_host: str
    smtp_port: int
    smtp_user: str | None
    smtp_password: str | None
    smtp_starttls: bool
    email_from: str
    email_to: list[str]


def load_classify_config() -> ClassifyConfig:
    return ClassifyConfig(
        db_path=_db_path(),
        ollama_url=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "minicpm-v4.6"),
        request_timeout=float(os.environ.get("OLLAMA_TIMEOUT", "120")),
        # Downscale screenshots to this longest edge before sending; keeps big
        # captures under a small vision model's context window. 0 = full size.
        image_max_edge=int(os.environ.get("OLLAMA_IMAGE_MAX_EDGE", "1280")),
        report_tz=os.environ.get("REPORT_TZ") or None,
    )


def load_report_config() -> ReportConfig:
    return ReportConfig(
        db_path=_db_path(),
        poll_interval_minutes=float(os.environ.get("POLL_INTERVAL_MINUTES", "10")),
        report_tz=os.environ.get("REPORT_TZ") or None,
        smtp_host=os.environ["SMTP_HOST"],
        smtp_port=int(os.environ.get("SMTP_PORT", "587")),
        smtp_user=os.environ.get("SMTP_USER") or None,
        smtp_password=os.environ.get("SMTP_PASSWORD") or None,
        # STARTTLS on by default (port 587); set SMTP_STARTTLS=false for a plain
        # or already-implicit-TLS connection.
        smtp_starttls=os.environ.get("SMTP_STARTTLS", "true").strip().lower() not in ("false", "0", "no"),
        email_from=os.environ["EMAIL_FROM"],
        email_to=_split_recipients(os.environ.get("EMAIL_TO", "")),
    )
