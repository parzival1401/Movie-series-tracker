import os
import json
import re
from datetime import datetime, date, timedelta
from typing import Callable

from groq import Groq

_client = None

TASTE_PROFILE = """
I watch a mix of anime and western content.

For anime: I love romance, slice-of-life, action shonen, and psychological series. Top favorites include Steins;Gate, Assassination Classroom, Frieren, Chainsaw Man, Angel Beats, Plastic Memories, Erased, and Your Lie in April.

For western content: I enjoy sci-fi, dystopian, time-travel, puzzle-thrillers, and animated series. Top favorites include Dark, Alice in Borderland, Arcane, Bojack Horseman, Gravity Falls, Star Wars series, and Dune.

For movies: I enjoy action, adventure, superhero, animated Disney/Pixar, Spider-Man films, Star Wars, and emotional sci-fi like Soul and Wall-E.

I rate things I genuinely enjoy 9-10, solid watches 7-8, and disappointing ones below 7.
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
    top_watched = sorted(
        [w for w in watched_list if w.get("rating")],
        key=lambda x: x["rating"],
        reverse=True,
    )[:20]

    loved = [w["title"] for w in top_watched if w.get("rating", 0) >= 9]
    liked = [w["title"] for w in top_watched if w.get("rating", 0) in (7, 8)]

    filter_context = ""
    if filter_genre or filter_type:
        parts = []
        if filter_type:
            parts.append(filter_type)
        if filter_genre:
            parts.append(filter_genre)
        filter_context = f"FILTER: Only recommend {' '.join(parts)} titles.\n"

    candidates_text = "\n".join(
        f"{i+1}. [{c.get('tmdb_id')}] {c.get('title', '')} "
        f"({c.get('year', '')}) {(c.get('genres') or '')[:40]} — "
        f"{(c.get('overview') or '')[:60]}"
        for i, c in enumerate(candidates[:15])
    )

    return f"""Movie recommender. {filter_context}
User loved: {', '.join(loved[:10])}
User liked: {', '.join(liked[:10])}
Taste: {TASTE_PROFILE.strip()[:200]}

Rate these candidates (return top 8 as JSON only):
{candidates_text}

JSON array, no markdown:
[{{"tmdb_id":int,"title":"str","score":float,"reason":"max 10 words"}}]"""


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

        candidate_meta = {c["tmdb_id"]: c for c in candidates if c.get("tmdb_id")}
        enriched = []
        for item in valid:
            meta = candidate_meta.get(item["tmdb_id"], {})
            enriched.append({
                **item,
                "type": meta.get("type") or filter_type or "movie",
                "year": meta.get("year"),
                "poster_url": meta.get("poster_url"),
                "genres": meta.get("genres") or "",
                "overview": meta.get("overview") or "",
            })
        return enriched

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
    all_valid = [w for w in watched_list if w.get("tmdb_id") and w.get("rating")]

    if filter_type:
        type_seeds = [w for w in all_valid if w.get("type", "").lower() == filter_type.lower()]
        seed_pool = type_seeds if len(type_seeds) >= 5 else all_valid
    else:
        seed_pool = all_valid

    if filter_genre:
        genre_seeds = sorted(
            [w for w in seed_pool if filter_genre.lower() in (w.get("genres") or "").lower()],
            key=lambda x: x["rating"],
            reverse=True,
        )[:20]
        if len(genre_seeds) < 5:
            other = sorted(
                [w for w in seed_pool if w not in genre_seeds],
                key=lambda x: x["rating"],
                reverse=True,
            )[:10]
            seed_titles = genre_seeds + other
        else:
            seed_titles = genre_seeds
    else:
        seed_titles = sorted(seed_pool, key=lambda x: x["rating"], reverse=True)[:30]

    print(f"Using {len(seed_titles)} seed titles for aggregation")

    scored: dict[int, float] = {}
    scored_meta: dict[int, dict] = {}

    for title in seed_titles:
        candidates = get_recommendations_fn(title["tmdb_id"], title.get("type", "movie"))
        weight = (title["rating"] or 5) / 10.0
        if filter_genre and filter_genre.lower() in (title.get("genres") or "").lower():
            weight *= 1.5
        for c in candidates:
            cid = c.get("tmdb_id")
            if not cid:
                continue
            if cid not in scored:
                scored[cid] = 0.0
                scored_meta[cid] = c
            scored[cid] += weight

    # Boost genre-matching candidates; no hard type filter (TMDB type field unreliable)
    if filter_genre:
        for cid in list(scored.keys()):
            if filter_genre.lower() in (scored_meta[cid].get("genres") or "").lower():
                scored[cid] *= 2.0

    top = sorted(scored.items(), key=lambda x: x[1], reverse=True)[:15]
    result = [scored_meta[cid] for cid, _ in top]
    print(f"Final candidates: {len(result)}")
    return result
