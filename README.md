# movie-rec

Personal movie and TV series tracker with AI recommendations.

## Requirements

- Docker + Docker Compose
- TMDB API bearer token
- Gemini API key

## Setup

```bash
cp .env.example .env
# fill in TMDB_BEARER_TOKEN and GEMINI_API_KEY in .env
```

## Run locally (Mac)

```bash
docker compose up --build
```

App available at http://localhost:8000

## Deploy to Raspberry Pi

```bash
git pull
docker compose up --build -d
```

App available via Tailscale at http://100.77.67.90:8000

## Import existing data

```bash
python scripts/import_csv.py path/to/data.csv
```

CSV columns: `tmdb_id, media_type, title, poster_path, rating, notes, watched_at`
