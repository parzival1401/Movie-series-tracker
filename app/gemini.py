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


def build_prompt(watched_list: list[dict], candidates: list[dict]) -> str:
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

CANDIDATES:
{candidate_lines}

Return ONLY a JSON array of the top 10 recommendations, no markdown, no explanation outside JSON.
Each object must have exactly these keys: tmdb_id (integer), title (string), score (float 0-10), reason (string, one sentence max).
Order by score descending."""


def rerank_recommendations(watched_list: list[dict], candidates: list[dict]):
    if not candidates:
        return []
    try:
        prompt = build_prompt(watched_list, candidates)

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
) -> list[dict]:
    scored: dict[int, dict] = {}

    for watched in watched_list:
        tmdb_id = watched.get("tmdb_id")
        rating = watched.get("rating")
        media_type = watched.get("type")
        if not tmdb_id or not rating or not media_type:
            continue

        weight = rating / 10.0
        candidates = get_recommendations_fn(tmdb_id, media_type)

        for c in candidates:
            cid = c.get("tmdb_id")
            if not cid:
                continue
            if cid not in scored:
                scored[cid] = {**c, "raw_score": 0.0}
            scored[cid]["raw_score"] += weight

    sorted_candidates = sorted(scored.values(), key=lambda x: x["raw_score"], reverse=True)
    return sorted_candidates[:20]
