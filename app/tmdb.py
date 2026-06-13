import os
import requests

TMDB_BASE = "https://api.themoviedb.org/3"


def _headers() -> dict:
    token = os.getenv("TMDB_BEARER_TOKEN", "")
    return {"Authorization": f"Bearer {token}", "accept": "application/json"}


def search(query: str, media_type: str = "multi") -> list[dict]:
    url = f"{TMDB_BASE}/search/{media_type}"
    r = requests.get(url, headers=_headers(), params={"query": query, "page": 1}, timeout=10)
    r.raise_for_status()
    return r.json().get("results", [])


def get_details(tmdb_id: int, media_type: str) -> dict:
    url = f"{TMDB_BASE}/{media_type}/{tmdb_id}"
    r = requests.get(url, headers=_headers(), timeout=10)
    r.raise_for_status()
    return r.json()


def get_similar(tmdb_id: int, media_type: str) -> list[dict]:
    url = f"{TMDB_BASE}/{media_type}/{tmdb_id}/similar"
    r = requests.get(url, headers=_headers(), params={"page": 1}, timeout=10)
    r.raise_for_status()
    return r.json().get("results", [])
