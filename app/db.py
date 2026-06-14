import sqlite3
from datetime import date
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "watched.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watched (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                title           TEXT    NOT NULL,
                type            TEXT    NOT NULL CHECK(type IN ('movie', 'series')),
                tmdb_id         INTEGER UNIQUE,
                year            INTEGER,
                poster_url      TEXT,
                genres          TEXT,
                rating          INTEGER CHECK(rating BETWEEN 1 AND 10),
                seasons_watched TEXT,
                date_added      TEXT,
                notes           TEXT
            )
        """)
        for col, definition in [
            ("source",      "TEXT DEFAULT 'tmdb'"),
            ("external_id", "INTEGER"),
        ]:
            try:
                conn.execute(f"ALTER TABLE watched ADD COLUMN {col} {definition}")
            except sqlite3.OperationalError:
                pass

        conn.execute("""
            CREATE TABLE IF NOT EXISTS recommendations (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                tmdb_id        INTEGER,
                title          TEXT,
                type           TEXT,
                year           INTEGER,
                poster_url     TEXT,
                genres         TEXT,
                overview       TEXT,
                score          REAL,
                reason         TEXT,
                generated_date TEXT,
                seen           INTEGER DEFAULT 0
            )
        """)
        conn.commit()


def add_watched(
    title: str,
    type: str,
    tmdb_id: int | None,
    year: int | None,
    poster_url: str | None,
    genres: str | None,
    rating: int | None,
    seasons_watched: str | None,
    notes: str | None,
    source: str = "tmdb",
    external_id: int | None = None,
) -> int:
    with _connect() as conn:
        existing = conn.execute(
            "SELECT id FROM watched WHERE tmdb_id = ?", (tmdb_id,)
        ).fetchone()
        if existing:
            raise ValueError("Already in library")
        cursor = conn.execute(
            """
            INSERT INTO watched
                (title, type, tmdb_id, year, poster_url, genres, rating, seasons_watched,
                 date_added, notes, source, external_id)
            VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, type, tmdb_id, year, poster_url, genres, rating, seasons_watched,
             date.today().isoformat(), notes, source, external_id),
        )
        conn.commit()
        return cursor.lastrowid


def get_all_watched(filter_type: str | None = None) -> list[dict]:
    with _connect() as conn:
        if filter_type in ("movie", "series"):
            rows = conn.execute(
                "SELECT * FROM watched WHERE type = ? ORDER BY date_added DESC", (filter_type,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM watched ORDER BY date_added DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def get_watched_by_id(id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM watched WHERE id = ?", (id,)).fetchone()
    return dict(row) if row else None


def get_watched_tmdb_ids() -> set[int]:
    with _connect() as conn:
        rows = conn.execute("SELECT tmdb_id FROM watched WHERE tmdb_id IS NOT NULL").fetchall()
    return {r["tmdb_id"] for r in rows}


def save_recommendations(recs: list[dict]) -> None:
    today = date.today().isoformat()
    with _connect() as conn:
        conn.execute("DELETE FROM recommendations")
        conn.executemany(
            """
            INSERT INTO recommendations
                (tmdb_id, title, type, year, poster_url, genres, overview, score, reason, generated_date)
            VALUES
                (:tmdb_id, :title, :type, :year, :poster_url, :genres, :overview, :score, :reason, :generated_date)
            """,
            [{**r, "generated_date": today} for r in recs],
        )
        conn.commit()


def get_recommendations() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM recommendations ORDER BY score DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_last_rec_date() -> str | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT MAX(generated_date) AS d FROM recommendations"
        ).fetchone()
    return row["d"] if row else None


def mark_seen(rec_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE recommendations SET seen = 1 WHERE id = ?", (rec_id,))
        conn.commit()


def delete_watched(id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM watched WHERE id = ?", (id,))
        conn.commit()
