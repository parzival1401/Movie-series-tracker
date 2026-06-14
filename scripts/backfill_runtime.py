import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app import db, tmdb

db.init_db()


def backfill():
    watched = db.get_all_watched()

    needs_update = [
        w for w in watched
        if w.get("tmdb_id") and w.get("runtime") is None
    ]

    print(f"Titles needing runtime data: {len(needs_update)}")

    updated = 0
    failed = 0

    for w in needs_update:
        data = tmdb.get_runtime_and_seasons(
            w["tmdb_id"], w.get("type", "movie")
        )

        if data["runtime"] or data["total_seasons"]:
            with db._connect() as conn:
                conn.execute(
                    """UPDATE watched SET
                       runtime = ?,
                       total_seasons = ?,
                       episodes_per_season = ?
                       WHERE id = ?""",
                    (data["runtime"], data["total_seasons"],
                     data["episodes_per_season"], w["id"]),
                )
                conn.commit()
            updated += 1
            print(f"  ✓ {w['title']}: runtime={data['runtime']}min "
                  f"seasons={data['total_seasons']} "
                  f"eps/season={data['episodes_per_season']}")
        else:
            failed += 1
            print(f"  ✗ {w['title']}: no data")

    print(f"\nDone. Updated: {updated} | No data: {failed}")


if __name__ == "__main__":
    backfill()
