import re
import time
import requests

_ENDPOINT = "https://graphql.anilist.co"

_ANIME_SUFFIXES = {"-san", "-kun", "-chan", "-sama", "-senpai", "-sensei"}
_ANIME_PARTICLES = {" no ", " wa ", " ga ", " ni ", " wo "}
_ANIME_WORDS = {"tensei", "isekai", "shounen", "seinen", "shoujo", "anime", "manga", "otaku", "mecha", "kawaii"}

_SEARCH_QUERY = """
query ($search: String) {
  Media(search: $search, type: ANIME, sort: SEARCH_MATCH) {
    id
    title { romaji english native }
    startDate { year }
    episodes
    coverImage { large }
    genres
    description(asHtml: false)
    format
  }
}
"""


def is_likely_anime(title: str) -> bool:
    lower = title.lower()
    if any(s in lower for s in _ANIME_SUFFIXES):
        return True
    if any(p in lower for p in _ANIME_PARTICLES):
        return True
    if any(w in lower for w in _ANIME_WORDS):
        return True
    return False


def search_anilist(title: str) -> dict | None:
    try:
        r = requests.post(
            _ENDPOINT,
            json={"query": _SEARCH_QUERY, "variables": {"search": title}},
            timeout=10,
        )
        time.sleep(0.25)
        r.raise_for_status()
        media = r.json().get("data", {}).get("Media")
        if not media:
            return None

        fmt = media.get("format", "")
        media_type = "movie" if fmt == "MOVIE" else "series"

        titles = media.get("title") or {}
        display_title = titles.get("english") or titles.get("romaji") or title

        genres = ", ".join(media.get("genres") or [])

        raw_desc = media.get("description") or ""
        overview = re.sub(r"<[^>]+>", "", raw_desc).strip()

        cover = (media.get("coverImage") or {}).get("large")
        year = (media.get("startDate") or {}).get("year")

        return {
            "tmdb_id": None,
            "external_id": media["id"],
            "title": display_title,
            "year": year,
            "poster_url": cover,
            "genres": genres,
            "overview": overview,
            "source": "anilist",
            "type": media_type,
        }
    except Exception:
        return None


def find_title(title: str, media_type: str) -> dict | None:
    from app.tmdb import smart_search_tmdb

    result = smart_search_tmdb(title, media_type)
    if result:
        return result

    if is_likely_anime(title):
        result = search_anilist(title)
        if result:
            return result

    return None
