import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS screenshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    captured_at TEXT NOT NULL,
    monitor_index INTEGER NOT NULL,
    window_title TEXT,
    file_path TEXT NOT NULL UNIQUE,
    label TEXT
);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    return conn


def insert_screenshot(
    conn: sqlite3.Connection,
    captured_at: str,
    monitor_index: int,
    window_title: str | None,
    file_path: str,
) -> None:
    conn.execute(
        "INSERT INTO screenshots (captured_at, monitor_index, window_title, file_path) VALUES (?, ?, ?, ?)",
        (captured_at, monitor_index, window_title, file_path),
    )
    conn.commit()
