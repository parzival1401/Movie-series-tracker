import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from app import db
from app.anilist import find_title

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

    added_tmdb = 0
    added_anilist = 0
    skipped_not_found = 0
    skipped_duplicate = 0

    for row in rows:
        title = row["title"].strip()
        media_type = row["type"].strip()
        csv_year = int(row["year"].strip()) if row.get("year", "").strip() else None
        rating = int(row["rating"].strip()) if row.get("rating", "").strip() else None
        seasons_watched = row.get("seasons_watched", "").strip() or None
        notes = row.get("notes", "").strip() or None

        print(f"Searching for: {title} ({media_type})...")

        result = find_title(title, media_type)

        if result is None:
            print(f"  ✗ Not found on any API — add manually at /add/manual")
            skipped_not_found += 1
            time.sleep(0.5)
            continue

        source = result.get("source", "tmdb")
        external_id = result.get("external_id")
        tmdb_id = result.get("tmdb_id")

        source_label = "AniList" if source == "anilist" else "TMDB"
        print(f"  ✓ Found on {source_label}: {result['title']} ({result['year']})")

        if args.dry_run:
            print(f"  [dry-run] Would add: source={source}, rating={rating}, seasons={seasons_watched}, notes={notes}")
            if source == "anilist":
                added_anilist += 1
            else:
                added_tmdb += 1
            time.sleep(0.5)
            continue

        try:
            db.add_watched(
                title=result["title"],
                type=media_type,
                tmdb_id=tmdb_id,
                year=csv_year or result["year"],
                poster_url=result["poster_url"],
                genres=result["genres"],
                rating=rating,
                seasons_watched=seasons_watched,
                notes=notes,
                source=source,
                external_id=external_id,
            )
            print("  ✓ Added.")
            if source == "anilist":
                added_anilist += 1
            else:
                added_tmdb += 1
        except ValueError:
            print("  → Already in library, skipping.")
            skipped_duplicate += 1

        time.sleep(0.5)

    suffix = " (dry-run)" if args.dry_run else ""
    not_found_note = f" (add these manually at /add/manual)" if skipped_not_found else ""
    print(
        f"\nDone{suffix}. "
        f"Added via TMDB: {added_tmdb} | "
        f"Added via AniList: {added_anilist} | "
        f"Not found: {skipped_not_found}{not_found_note}"
    )


if __name__ == "__main__":
    main()
