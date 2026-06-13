import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "/app/data/watched.db")


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watched (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tmdb_id INTEGER NOT NULL,
                media_type TEXT NOT NULL CHECK(media_type IN ('movie', 'tv')),
                title TEXT NOT NULL,
                poster_path TEXT,
                rating INTEGER CHECK(rating BETWEEN 1 AND 10),
                notes TEXT,
                watched_at TEXT DEFAULT (date('now')),
                added_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%S', 'now'))
            )
        """)
        conn.commit()
