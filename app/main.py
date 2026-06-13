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
    return templates.TemplateResponse(
        request=request,
        name="library.html",
        context={"items": items, "current_filter": filter, "error": error},
    )


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@app.get("/search")
def search(request: Request):
    return templates.TemplateResponse(request=request, name="search.html", context={})


@app.get("/api/search")
def api_search(q: str, type: str = "movie"):
    if type not in ("movie", "series"):
        return JSONResponse([])
    result = tmdb.search_title(q, type)
    if result is None:
        return JSONResponse([])
    return JSONResponse([result])


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
# Similar
# ---------------------------------------------------------------------------

@app.get("/similar/{tmdb_id}/{media_type}")
def similar(request: Request, tmdb_id: int, media_type: str):
    watched_ids = db.get_watched_tmdb_ids()
    results = tmdb.get_recommendations(tmdb_id, media_type)
    results = [r for r in results if r["tmdb_id"] not in watched_ids]
    source = tmdb.get_details(tmdb_id, media_type) or {}
    return templates.TemplateResponse(
        request=request,
        name="similar.html",
        context={"source_title": source, "results": results},
    )


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def _build_and_save_recs():
    watched = db.get_all_watched()
    watched_ids = db.get_watched_tmdb_ids()
    candidates = gemini.aggregate_tmdb_recs(watched, tmdb.get_recommendations)
    candidates = [c for c in candidates if c["tmdb_id"] not in watched_ids]
    final = gemini.rerank_recommendations(watched, candidates)
    candidate_map = {c["tmdb_id"]: c for c in candidates}
    for item in final:
        if not item.get("poster_url"):
            item["poster_url"] = candidate_map.get(item["tmdb_id"], {}).get("poster_url")
    db.save_recommendations(final)


@app.get("/recommendations")
def recommendations(request: Request):
    last_date = db.get_last_rec_date()
    if gemini.should_refresh(last_date):
        _build_and_save_recs()
    recs = db.get_recommendations()
    last_date = db.get_last_rec_date()
    return templates.TemplateResponse(
        request=request,
        name="recommendations.html",
        context={"recs": recs, "last_date": last_date},
    )


@app.post("/recommendations/refresh")
def recommendations_refresh():
    _build_and_save_recs()
    return RedirectResponse("/recommendations", status_code=303)


@app.post("/recommendations/seen/{id}")
def mark_seen(id: int):
    db.mark_seen(id)
    return JSONResponse({"success": True})
