import os
import time
import requests
from itertools import zip_longest

_BASE = "https://api.themoviedb.org/3"
_POSTER_BASE = "https://image.tmdb.org/t/p/w300"
_LOGO_BASE = "https://image.tmdb.org/t/p/w45"

_genre_cache: dict[str, dict[int, str]] = {"movie": {}, "series": {}}
_provider_cache: dict[tuple, dict] = {}


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {os.getenv('TMDB_BEARER_TOKEN', '')}",
        "accept": "application/json",
    }


def _get(url: str, params: dict | None = None):
    try:
        r = requests.get(url, headers=_headers(), params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def fetch_genres(media_type: str) -> None:
    endpoint = "movie" if media_type == "movie" else "tv"
    data = _get(f"{_BASE}/genre/{endpoint}/list")
    if not data:
        return
    _genre_cache[media_type] = {g["id"]: g["name"] for g in data.get("genres", [])}


def genre_ids_to_names(genre_ids: list[int], media_type: str) -> str:
    if not _genre_cache[media_type]:
        fetch_genres(media_type)
    cache = _genre_cache[media_type]
    return ", ".join(cache[gid] for gid in genre_ids if gid in cache)


def _map_result(item: dict, media_type: str) -> dict:
    poster = item.get("poster_path")
    raw_date = item.get("release_date") if media_type == "movie" else item.get("first_air_date")
    year = int(raw_date[:4]) if raw_date and len(raw_date) >= 4 else None
    return {
        "tmdb_id": item["id"],
        "title": item.get("title") if media_type == "movie" else item.get("name"),
        "year": year,
        "poster_url": f"{_POSTER_BASE}{poster}" if poster else None,
        "overview": item.get("overview"),
        "genres": genre_ids_to_names(item.get("genre_ids", []), media_type),
    }


def _search_raw(name: str, media_type: str) -> list[dict]:
    endpoint = "movie" if media_type == "movie" else "tv"
    data = _get(f"{_BASE}/search/{endpoint}", params={"query": name, "include_adult": False, "page": 1})
    if not data:
        return []
    results = data.get("results", [])
    mapped = []
    for r in results[:8]:
        item = _map_result(r, media_type)
        item["type"] = media_type
        item["vote_average"] = round(r.get("vote_average", 0), 1)
        item["source"] = "tmdb"
        mapped.append(item)
    time.sleep(0.25)
    return mapped


def _search_endpoint(query: str, media_type: str) -> dict | None:
    results = _search_raw(query, media_type)
    return results[0] if results else None


def search_titles_multi(name: str, media_type: str, max_results: int = 8) -> list[dict]:
    if not name.strip():
        return []
    if media_type == "both":
        movie_results = _search_raw(name, "movie")
        series_results = _search_raw(name, "series")
        combined = []
        for pair in zip_longest(movie_results, series_results):
            combined.extend(r for r in pair if r is not None)
        return combined[:max_results]
    return _search_raw(name, media_type)[:max_results]


def _search_title_single(query: str, media_type: str) -> dict | None:
    return _search_endpoint(query, media_type)


def smart_search_tmdb(title: str, media_type: str) -> dict | None:
    result = _search_endpoint(title, media_type)
    if result:
        return result

    if ":" in title:
        time.sleep(0.25)
        after_colon = title.split(":", 1)[1].strip()
        result = _search_endpoint(after_colon, media_type)
        if result:
            return result

    time.sleep(0.25)
    alt_type = "series" if media_type == "movie" else "movie"
    return _search_endpoint(title, alt_type)


def search_title(name: str, media_type: str) -> dict | None:
    return smart_search_tmdb(name, media_type)


def get_recommendations(tmdb_id: int, media_type: str) -> list[dict]:
    endpoint = "movie" if media_type == "movie" else "tv"

    data = _get(f"{_BASE}/{endpoint}/{tmdb_id}/recommendations", params={"page": 1})
    results = data.get("results", []) if data else []

    if len(results) < 10:
        time.sleep(0.25)
        sim_data = _get(f"{_BASE}/{endpoint}/{tmdb_id}/similar", params={"page": 1})
        if sim_data:
            seen_ids = {r["id"] for r in results}
            for item in sim_data.get("results", []):
                if item["id"] not in seen_ids:
                    results.append(item)
                    seen_ids.add(item["id"])

    return [_map_result(item, media_type) for item in results[:20]]


def get_watch_providers(tmdb_id: int, media_type: str, country_code: str | None = None) -> dict:
    if country_code is None:
        country_code = os.getenv("WATCH_PROVIDER_COUNTRY", "US")
    cache_key = (tmdb_id, media_type, country_code)
    if cache_key in _provider_cache:
        return _provider_cache[cache_key]

    empty = {"stream": [], "rent": [], "buy": [], "link": None}
    endpoint = "movie" if media_type == "movie" else "tv"
    time.sleep(0.25)
    data = _get(f"{_BASE}/{endpoint}/{tmdb_id}/watch/providers")
    if not data:
        _provider_cache[cache_key] = empty
        return empty

    country = data.get("results", {}).get(country_code, {})
    if not country:
        _provider_cache[cache_key] = empty
        return empty

    def _extract(key: str) -> list[dict]:
        return [
            {"provider_name": p["provider_name"], "logo_path": f"{_LOGO_BASE}{p['logo_path']}"}
            for p in country.get(key, [])
            if p.get("logo_path")
        ]

    result = {
        "stream": _extract("flatrate"),
        "rent": _extract("rent"),
        "buy": _extract("buy"),
        "link": country.get("link"),
    }
    _provider_cache[cache_key] = result
    return result


def get_details(tmdb_id: int, media_type: str) -> dict | None:
    endpoint = "movie" if media_type == "movie" else "tv"
    data = _get(f"{_BASE}/{endpoint}/{tmdb_id}")
    if not data:
        return None

    poster = data.get("poster_path")
    raw_date = data.get("release_date") if media_type == "movie" else data.get("first_air_date")
    year = int(raw_date[:4]) if raw_date and len(raw_date) >= 4 else None
    genres = ", ".join(g["name"] for g in data.get("genres", []))
    title = data.get("title") if media_type == "movie" else data.get("name")

    return {
        "tmdb_id": data["id"],
        "title": title,
        "year": year,
        "poster_url": f"{_POSTER_BASE}{poster}" if poster else None,
        "overview": data.get("overview"),
        "genres": genres,
        "vote_average": data.get("vote_average"),
        "tagline": data.get("tagline"),
    }
