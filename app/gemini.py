import json
import os
from datetime import date, timedelta
from typing import Callable

from google import genai
from google.genai import types

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY", ""))
_MODEL = "gemini-2.0-flash"

TASTE_PROFILE = """
[I WILL FILL THIS IN — DO NOT CHANGE THIS LINE]
"""


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


def rerank_recommendations(watched_list: list[dict], candidates: list[dict]) -> list[dict]:
    try:
        prompt = build_prompt(watched_list, candidates)
        response = _client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.7,
                max_output_tokens=2000,
            ),
        )
        text = response.text.strip()

        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]

        parsed = json.loads(text)
        required = {"tmdb_id", "title", "score", "reason"}
        validated = [item for item in parsed if required.issubset(item.keys())]
        return validated
    except Exception:
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
