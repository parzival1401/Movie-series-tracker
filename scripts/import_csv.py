"""
Import watched items from a CSV file into the database.

CSV columns (order matters): tmdb_id, media_type, title, poster_path, rating, notes, watched_at

Usage:
    python scripts/import_csv.py path/to/file.csv
"""
import csv
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from app.db import get_conn, init_db


def import_csv(path: str) -> None:
    init_db()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    with get_conn() as conn:
        for row in rows:
            conn.execute(
                """
                INSERT INTO watched (tmdb_id, media_type, title, poster_path, rating, notes, watched_at)
                VALUES (:tmdb_id, :media_type, :title, :poster_path, :rating, :notes, :watched_at)
                """,
                {
                    "tmdb_id": int(row["tmdb_id"]),
                    "media_type": row["media_type"],
                    "title": row["title"],
                    "poster_path": row.get("poster_path") or None,
                    "rating": int(row["rating"]) if row.get("rating") else None,
                    "notes": row.get("notes") or None,
                    "watched_at": row.get("watched_at") or None,
                },
            )
        conn.commit()
    print(f"Imported {len(rows)} rows from {path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/import_csv.py <file.csv>")
        sys.exit(1)
    import_csv(sys.argv[1])
