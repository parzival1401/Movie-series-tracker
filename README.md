# movie-rec

Personal movie and TV tracker with AI recommendations. Runs on a Raspberry Pi via Docker.

## First-time setup on Pi

```bash
git clone https://github.com/parzival1401/Movie-series-tracker.git
cd Movie-series-tracker
cp .env.example .env
```

Fill in `.env`:
- `TMDB_BEARER_TOKEN` — get at themoviedb.org/settings/api
- `GEMINI_API_KEY` — get at aistudio.google.com

```bash
mkdir data
chmod +x deploy.sh
./deploy.sh
```

## Import existing watched titles

Create `watched.csv` in the project root:

```
title,type,year,rating,seasons_watched,notes
Inception,movie,2010,9,,
Breaking Bad,series,2008,10,"1,2,3,4,5",
```

```bash
# Dry run first
docker compose exec movie-rec python scripts/import_csv.py --dry-run

# Then import
docker compose exec movie-rec python scripts/import_csv.py
```

## Daily usage

- Access at http://100.77.67.90:8000 from any device on Tailscale
- Updates: `git push` from Mac, then `./deploy.sh` on Pi

## Updating your taste profile

- Edit `TASTE_PROFILE` in `app/gemini.py`
- Redeploy with `./deploy.sh`
- Go to `/recommendations` and click Refresh
