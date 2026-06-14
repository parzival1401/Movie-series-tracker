import os
import json
import re
from datetime import datetime, date, timedelta
from typing import Callable

from groq import Groq

_client = None

TASTE_PROFILE = """
[I WILL FILL THIS IN — DO NOT CHANGE THIS LINE]
"""


def get_client():
    global _client
    if _client is None:
        _client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _client


def should_refresh(last_date: str | None) -> bool:
    if last_date is None:
        return True
    try:
        last = date.fromisoformat(last_date)
    except ValueError:
        return True
    return (date.today() - last) > timedelta(days=7)


def build_prompt(
    watched_list: list[dict],
    candidates: list[dict],
    filter_genre: str | None = None,
    filter_type: str | None = None,
) -> str:
    loved = [w for w in watched_list if w.get("rating") and w["rating"] >= 9]
    liked = [w for w in watched_list if w.get("rating") and 7 <= w["rating"] <= 8]
    mixed = [w for w in watched_list if w.get("rating") and w["rating"] <= 6]

    def fmt(w: dict) -> str:
        parts = f"{w['title']} ({w['type']}) — {w.get('genres', '')}"
        if w.get("notes"):
            parts += f" — {w['notes']}"
        return parts

    loved_lines = "\n".join(f"  {fmt(w)}" for w in loved) or "  (none)"
    liked_lines = "\n".join(f"  {fmt(w)}" for w in liked) or "  (none)"
    mixed_lines = "\n".join(f"  {fmt(w)}" for w in mixed) or "  (none)"

    candidate_lines = "\n".join(
        f"{i+1}. {c['title']} ({c.get('year', '?')}) [{c.get('type', '')}] — {c.get('genres', '')}\n"
        f"   {c.get('overview', '')}"
        for i, c in enumerate(candidates[:20])
    )

    filter_context = ""
    if filter_genre or filter_type:
        parts = []
        if filter_type:
            parts.append(f"type: {filter_type}")
        if filter_genre:
            parts.append(f"genre: {filter_genre}")
        filter_context = f"""
ACTIVE FILTERS: The user specifically wants recommendations filtered by {' and '.join(parts)}.
Prioritize candidates that match these filters.
Only recommend titles that match the filter criteria.
"""

    return f"""You are a recommendation engine. Rerank the 20 candidate titles below for this user.

USER'S WATCH HISTORY:
Loved (9-10):
{loved_lines}

Liked (7-8):
{liked_lines}

Mixed (1-6):
{mixed_lines}

TASTE PROFILE:
{TASTE_PROFILE.strip()}
{filter_context}
CANDIDATES:
{candidate_lines}

Return ONLY a JSON array of the top 10 recommendations, no markdown, no explanation outside JSON.
Each object must have exactly these keys: tmdb_id (integer), title (string), score (float 0-10), reason (string, one sentence max).
Order by score descending."""


def rerank_recommendations(
    watched_list: list[dict],
    candidates: list[dict],
    filter_genre: str | None = None,
    filter_type: str | None = None,
):
    if not candidates:
        return []
    try:
        prompt = build_prompt(watched_list, candidates, filter_genre, filter_type)

        response = get_client().chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=2000,
        )

        text = response.choices[0].message.content
        text = re.sub(r"```json\s*", "", text)
        text = re.sub(r"```\s*", "", text)
        text = text.strip()

        parsed = json.loads(text)
        required = {"tmdb_id", "title", "score", "reason"}
        valid = [item for item in parsed if required.issubset(item.keys())]
        return valid

    except Exception as e:
        error_str = str(e)
        if "429" in error_str or "rate_limit" in error_str.lower():
            print(f"Groq rate limit hit: {e}")
            return "quota_exceeded"
        print(f"Groq error: {e}")
        return []


def aggregate_tmdb_recs(
    watched_list: list[dict],
    get_recommendations_fn: Callable[[int, str], list[dict]],
    filter_genre: str | None = None,
    filter_type: str | None = None,
) -> list[dict]:
    # Seed titles: filter by type if requested, fall back to all if too few
    seed_titles = watched_list
    if filter_type:
        type_filtered = [w for w in seed_titles if w.get("type", "").lower() == filter_type.lower()]
        if len(type_filtered) >= 5:
            seed_titles = type_filtered

    if filter_genre:
        genre_filtered = [
            w for w in seed_titles
            if w.get("genres") and filter_genre.lower() in w["genres"].lower()
        ]
        if len(genre_filtered) >= 3:
            seed_titles = genre_filtered

    # Sort by rating, take top 30
    seed_titles = sorted(
        [w for w in seed_titles if w.get("tmdb_id") and w.get("rating")],
        key=lambda x: x["rating"],
        reverse=True,
    )[:30]

    scored: dict[int, float] = {}
    scored_meta: dict[int, dict] = {}

    for title in seed_titles:
        candidates = get_recommendations_fn(title["tmdb_id"], title.get("type", "movie"))
        weight = (title["rating"] or 5) / 10.0
        for c in candidates:
            cid = c.get("tmdb_id")
            if not cid:
                continue
            if cid not in scored:
                scored[cid] = 0.0
                scored_meta[cid] = c
            scored[cid] += weight

    # Apply type filter to candidates
    if filter_type:
        scored = {
            cid: s for cid, s in scored.items()
            if scored_meta[cid].get("type", "").lower() == filter_type.lower()
        }

    # Apply genre filter to candidates
    if filter_genre:
        scored = {
            cid: s for cid, s in scored.items()
            if filter_genre.lower() in (scored_meta[cid].get("genres") or "").lower()
        }

    top = sorted(scored.items(), key=lambda x: x[1], reverse=True)[:20]
    return [scored_meta[cid] for cid, _ in top]
