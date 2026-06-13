import argparse
import csv
import sys
import time
from pathlib import Path

# Allow `from app import ...` when run from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app import db, tmdb

CSV_PATH = Path("watched.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bulk import watched titles from watched.csv")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing to DB")
    args = parser.parse_args()

    if not CSV_PATH.exists():
        print(f"Error: {CSV_PATH} not found. Run from the project root directory.")
        sys.exit(1)

    if not args.dry_run:
        db.init_db()

    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    added = 0
    skipped_not_found = 0
    skipped_duplicate = 0

    for row in rows:
        title = row["title"].strip()
        media_type = row["type"].strip()
        csv_year = int(row["year"].strip()) if row.get("year", "").strip() else None
        rating = int(row["rating"].strip()) if row.get("rating", "").strip() else None
        seasons_watched = row.get("seasons_watched", "").strip() or None
        notes = row.get("notes", "").strip() or None

        print(f"Searching TMDB for: {title} ({media_type})...")

        result = tmdb.search_title(title, media_type)

        if result is None:
            print("  ⚠ Not found on TMDB, skipping.")
            skipped_not_found += 1
            time.sleep(0.5)
            continue

        print(f"  ✓ Found: {result['title']} ({result['year']}) — TMDB ID: {result['tmdb_id']}")

        if args.dry_run:
            print(f"  [dry-run] Would add: rating={rating}, seasons={seasons_watched}, notes={notes}")
            added += 1
            time.sleep(0.5)
            continue

        try:
            db.add_watched(
                title=result["title"],
                type=media_type,
                tmdb_id=result["tmdb_id"],
                year=csv_year or result["year"],
                poster_url=result["poster_url"],
                genres=result["genres"],
                rating=rating,
                seasons_watched=seasons_watched,
                notes=notes,
            )
            print("  ✓ Added.")
            added += 1
        except ValueError:
            print("  → Already in library, skipping.")
            skipped_duplicate += 1

        time.sleep(0.5)

    suffix = " (dry-run)" if args.dry_run else ""
    print(f"\nDone{suffix}. Added: {added} | Skipped (not found): {skipped_not_found} | Skipped (duplicate): {skipped_duplicate}")


if __name__ == "__main__":
    main()
