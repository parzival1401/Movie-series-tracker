from contextlib import asynccontextmanager

from fastapi import FastAPI, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv()

from app import db, tmdb, gemini


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static", check_dir=False), name="static")
templates = Jinja2Templates(directory="app/templates")


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------

@app.get("/")
def index(request: Request):
    all_watched = db.get_all_watched()
    movie_count = sum(1 for w in all_watched if w["type"] == "movie")
    series_count = sum(1 for w in all_watched if w["type"] == "series")
    recent = all_watched[:5]
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"movie_count": movie_count, "series_count": series_count, "recent": recent},
    )


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

@app.get("/library")
def library(request: Request, filter: str | None = None, error: str | None = None):
    if filter not in ("movie", "series"):
        filter = None
    items = db.get_all_watched(filter_type=filter)
    all_genres: set[str] = set()
    for item in items:
        if item["genres"]:
            for g in item["genres"].split(","):
                genre = g.strip()
                if genre:
                    all_genres.add(genre)
    genres_list = sorted(all_genres)
    return templates.TemplateResponse(
        request=request,
        name="library.html",
        context={"items": items, "current_filter": filter, "error": error, "genres_list": genres_list},
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@app.get("/search")
def search(request: Request, q: str | None = None, type: str | None = None):
    return templates.TemplateResponse(
        request=request, name="search.html",
        context={"initial_q": q or "", "initial_type": type or "both"},
    )


@app.get("/api/search")
def api_search(q: str = "", type: str = "both"):
    if not q.strip():
        return JSONResponse([])
    if type not in ("movie", "series", "both"):
        type = "both"
    results = tmdb.search_titles_multi(q, type, max_results=8)
    return JSONResponse(results)


# ---------------------------------------------------------------------------
# Add / Delete watched
# ---------------------------------------------------------------------------

@app.post("/add")
def add_watched(
    tmdb_id: int = Form(...),
    title: str = Form(...),
    type: str = Form(...),
    year: int | None = Form(None),
    poster_url: str | None = Form(None),
    genres: str | None = Form(None),
    rating: int | None = Form(None),
    seasons_watched: str | None = Form(None),
    notes: str | None = Form(None),
):
    try:
        db.add_watched(
            title=title,
            type=type,
            tmdb_id=tmdb_id,
            year=year,
            poster_url=poster_url,
            genres=genres,
            rating=rating,
            seasons_watched=seasons_watched,
            notes=notes,
        )
    except ValueError:
        return RedirectResponse("/library?error=duplicate", status_code=303)
    return RedirectResponse("/library", status_code=303)


@app.delete("/watched/{id}")
def delete_watched(id: int):
    db.delete_watched(id)
    return JSONResponse({"success": True})


# ---------------------------------------------------------------------------
# Manual add (fallback for titles not found by any API)
# ---------------------------------------------------------------------------

@app.get("/add/manual")
def manual_add_form(request: Request, error: str | None = None):
    return templates.TemplateResponse(
        request=request,
        name="manual_add.html",
        context={"error": error},
    )


@app.post("/add/manual")
def manual_add_submit(
    title: str = Form(...),
    type: str = Form(...),
    year: int | None = Form(None),
    poster_url: str | None = Form(None),
    genres: str | None = Form(None),
    rating: int = Form(...),
    seasons_watched: str | None = Form(None),
    notes: str | None = Form(None),
):
    try:
        db.add_watched(
            title=title,
            type=type,
            tmdb_id=None,
            year=year,
            poster_url=poster_url or None,
            genres=genres or None,
            rating=rating,
            seasons_watched=seasons_watched or None,
            notes=notes or None,
            source="manual",
            external_id=None,
        )
    except ValueError:
        return RedirectResponse("/add/manual?error=duplicate", status_code=303)
    return RedirectResponse("/library", status_code=303)


# ---------------------------------------------------------------------------
# Similar
# ---------------------------------------------------------------------------

@app.get("/similar/{tmdb_id}/{media_type}")
def similar(request: Request, tmdb_id: int, media_type: str):
    watched_ids = db.get_watched_tmdb_ids()
    results = tmdb.get_recommendations(tmdb_id, media_type)
    results = [r for r in results if r["tmdb_id"] not in watched_ids]
    source = tmdb.get_details(tmdb_id, media_type) or {}
    source_providers = tmdb.get_watch_providers(tmdb_id, media_type)
    providers = {r["tmdb_id"]: tmdb.get_watch_providers(r["tmdb_id"], media_type) for r in results}
    return templates.TemplateResponse(
        request=request,
        name="similar.html",
        context={
            "source_title": source,
            "source_providers": source_providers,
            "results": results,
            "providers": providers,
        },
    )


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def _filter_key(genre: str | None, type: str | None) -> str:
    parts = []
    if genre:
        parts.append(f"genre:{genre.lower()}")
    if type:
        parts.append(f"type:{type.lower()}")
    return "|".join(parts) if parts else "all"


def _build_and_save_recs(
    genre: str | None = None,
    type: str | None = None,
) -> str | None:
    watched = db.get_all_watched()
    watched_ids = db.get_watched_tmdb_ids()

    top_watched = sorted(
        [w for w in watched if w.get("tmdb_id") and (w.get("rating") or 0) >= 7],
        key=lambda x: x["rating"],
        reverse=True,
    )[:30]

    print(f"Building recs — filter: genre={genre} type={type}")
    candidates = gemini.aggregate_tmdb_recs(
        top_watched, tmdb.get_recommendations,
        filter_genre=genre, filter_type=type,
    )
    candidates = [c for c in candidates if c.get("tmdb_id") not in watched_ids]

    print(f"Got {len(candidates)} candidates, calling Groq...")
    final = gemini.rerank_recommendations(watched, candidates, filter_genre=genre, filter_type=type)

    if final == "quota_exceeded":
        return "quota_exceeded"

    candidate_map = {c["tmdb_id"]: c for c in candidates}
    for item in final:
        if not item.get("poster_url"):
            item["poster_url"] = candidate_map.get(item.get("tmdb_id"), {}).get("poster_url")

    db.save_recommendations(final, filter_genre=genre, filter_type=type)
    return None


@app.get("/recommendations")
def recommendations(
    request: Request,
    genre: str | None = None,
    type: str | None = None,
):
    fkey = _filter_key(genre, type)

    # Never auto-run pipeline on GET — only serve cached results
    recs = db.get_recommendations(fkey)
    last_date = db.get_last_rec_date(fkey)

    providers = {}
    if recs:
        providers = {
            rec["tmdb_id"]: tmdb.get_watch_providers(rec["tmdb_id"], rec["type"])
            for rec in recs if rec.get("tmdb_id") and rec.get("type")
        }

    return templates.TemplateResponse(
        request=request,
        name="recommendations.html",
        context={
            "recs": recs,
            "last_date": last_date,
            "providers": providers,
            "error": None,
            "active_genre": genre,
            "active_type": type,
            "filter_key": fkey,
        },
    )


@app.post("/recommendations/refresh")
def recommendations_refresh(
    genre: str | None = Form(None),
    type: str | None = Form(None),
):
    fkey = _filter_key(genre, type)
    with db._connect() as conn:
        conn.execute("DELETE FROM recommendations WHERE filter_key = ?", (fkey,))
        conn.commit()
    params = []
    if genre:
        params.append(f"genre={genre}")
    if type:
        params.append(f"type={type}")
    redirect_url = "/recommendations" + (f"?{'&'.join(params)}" if params else "")
    return RedirectResponse(redirect_url, status_code=303)


@app.post("/recommendations/seen/{id}")
def mark_seen(id: int):
    db.mark_seen(id)
    return JSONResponse({"success": True})
