import sqlite3
from pathlib import Path


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open the shared metadata DB that the `server` component populates.

    The server owns the schema; the classifier only reads screenshot rows and
    fills in their ``label``, so it never creates tables. A busy timeout lets a
    concurrent poll write settle instead of raising ``database is locked``.
    """
    if not db_path.exists():
        raise FileNotFoundError(
            f"metadata database not found at {db_path} — is DB_PATH pointing at "
            "the server's SQLite file, and has poll-screenshots run yet?"
        )
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def fetch_unlabeled(conn: sqlite3.Connection, start_iso: str, end_iso: str) -> list[sqlite3.Row]:
    """Screenshots in the day's window that haven't been labelled yet."""
    return conn.execute(
        "SELECT id, file_path, window_title, captured_at FROM screenshots "
        "WHERE label IS NULL AND captured_at >= ? AND captured_at < ? "
        "ORDER BY captured_at",
        (start_iso, end_iso),
    ).fetchall()


def set_label(conn: sqlite3.Connection, screenshot_id: int, label: str) -> None:
    conn.execute("UPDATE screenshots SET label = ? WHERE id = ?", (label, screenshot_id))
    conn.commit()


def fetch_labels(conn: sqlite3.Connection, start_iso: str, end_iso: str) -> list[str]:
    """All non-null labels in the day's window, for aggregation."""
    rows = conn.execute(
        "SELECT label FROM screenshots "
        "WHERE label IS NOT NULL AND captured_at >= ? AND captured_at < ?",
        (start_iso, end_iso),
    ).fetchall()
    return [row["label"] for row in rows]


def count_failed_polls(conn: sqlite3.Connection, start_iso: str, end_iso: str) -> int:
    """How many polls failed in the window (each agent_status row is one failure).

    The poller only writes agent_status on a failed poll, so this is a simple
    proxy for monitoring gaps to surface in the report.
    """
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM agent_status WHERE checked_at >= ? AND checked_at < ?",
        (start_iso, end_iso),
    ).fetchone()
    return row["n"] if row else 0
