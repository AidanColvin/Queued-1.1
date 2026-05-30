# nextwatch

**AI-powered movie and TV recommendation engine.**  
Input titles you have loved. Get ranked suggestions from a hybrid ML pipeline trained on 25 million public ratings.

> Live demo → `nextwatch.vercel.app` · Backend → Render free tier

---

## What it does

You give NextWatch a list of movies or shows. It analyzes your taste across three axes — collaborative signal (what similar viewers watched), content signal (genre and tag overlap), and semantic signal (plot embedding similarity) — blends them into a single ranked list, and tells you *why* each title was recommended.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend (Next.js 14 · TypeScript · Tailwind · framer-motion)│
│                                                             │
│  SearchInput ──► /search   ──► autocomplete results          │
│  SwipeDeck   ──► /recommend ──► swipeable card deck           │
│      every swipe ──► /swipe ──► silent live re-rank           │
│  ResultsSummary ──► taste radar (recharts) + watchlist        │
└────────────────────────┬────────────────────────────────────┘
                         │ REST (JSON)
┌────────────────────────▼────────────────────────────────────┐
│  Backend (FastAPI · Python 3.11 · Uvicorn · Render)         │
│                                                             │
│  /recommend ──► HybridRecommender                           │
│                  ├── CollaborativeFilter  (SVD · 45%)       │
│                  ├── ContentFilter        (TF-IDF · 35%)    │
│                  └── SemanticFilter       (MiniLM · 20%)    │
│                                                             │
│  /swipe     ──► SessionReranker (Layer 1, in-memory)        │
│  /search    ──► local SQLite index (+ optional TMDB)        │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  Data layer                                                 │
│                                                             │
│  MovieLens 25M     25M ratings · 62K movies · 162K users   │
│  TMDB API          Poster URLs · genres · overviews         │
│  IMDb title.basics Canonical titles + years                 │
│  SQLite            movies · swipe_events · → Postgres        │
└─────────────────────────────────────────────────────────────┘
```

---

## ML pipeline

### Data
Training data is the [MovieLens 25M dataset](https://grouplens.org/datasets/movielens/25m/) (GroupLens public license). It contains 25 million explicit ratings from 162,000 users across 62,000 movies. Movie metadata (posters, overviews, genres) is fetched from the [TMDB API](https://www.themoviedb.org/documentation/api) (free tier). Title canonicalization uses IMDb's [publicly available TSV dumps](https://datasets.imdbws.com/).

### Models
**Collaborative filtering** (SVD via scikit-surprise). Learns latent factors from the user-item rating matrix. Given a set of seed movies, averages their item vectors and cosine-ranks all other items against that mean. Captures behavioral patterns that genre labels miss — e.g., "prestige TV with unreliable narrators."

**Content-based filtering** (TF-IDF cosine similarity). Builds a sparse matrix over genres, user-assigned tags, and plot keywords. Handles cold-start well — new titles without many ratings still surface if their metadata overlaps.

**Semantic similarity** (sentence-transformers `all-MiniLM-L6-v2`). Encodes TMDB plot overviews into 384-dim dense vectors. Finds thematically related titles even when genre tags diverge. Runs at inference time against precomputed embeddings stored as a numpy array.

### Hybrid blending
```python
score = 0.45 * cf_score + 0.35 * content_score + 0.20 * semantic_score
```
Weights were tuned empirically on a held-out 20% of the MovieLens test split. CF dominates because behavioral signal is the strongest predictor at this dataset scale. Semantic score adds diversity — prevents the list from collapsing to a single genre.

### Adaptive re-ranking (learns as you swipe)

The model never cold-starts against *you* — it ships trained on 25M ratings, so the first card is already good. From there it personalizes in real time. Each swipe nudges a per-session preference vector toward (or away from) the card's embedding, and the remaining deck is re-sorted by cosine similarity — pure numpy, ~milliseconds, **no retraining** ([`ml/reranker.py`](backend/ml/reranker.py)):

```python
SIGNAL_WEIGHTS = {"liked": 1.0, "saved": 0.65, "skip": -0.25, "dismissed": -0.55}
```

The signals are deliberately **asymmetric** — a dismiss is not the mirror of a like — and a `time_on_card_ms` modifier treats a fast dismiss as a confident "no" and a long hesitation as a soft "maybe". Every swipe is logged to `swipe_events` as the source of truth for periodic offline retraining (planned: ALS on implicit feedback). Cross-session user profiles arrive with accounts in Phase 3.

---

## API

### `POST /recommend`
```json
// request
{ "titles": ["The Wire", "Succession", "Severance"], "count": 10 }

// response
{
  "recommendations": [
    {
      "title": "Halt and Catch Fire",
      "year": 2014,
      "type": "tv",
      "score": 0.91,
      "genres": ["Drama", "History"],
      "poster_url": "https://image.tmdb.org/...",
      "why": "Matched on workplace tension, slow-burn arcs, prestige drama signals"
    }
  ],
  "taste_profile": {
    "top_genres": ["Drama", "Thriller"],
    "mood_tags": ["slow-burn", "workplace", "prestige"],
    "era_bias": "2010s"
  }
}
```

### `POST /swipe`
Records one swipe and returns the live re-ranked remaining deck. Anonymous (session-keyed); fire-and-forget from the UI.
```json
// request
{ "session_id": "…", "tmdb_id": 1396, "action": "liked", "time_on_card_ms": 1800, "remaining": [1438, 2316, 8592] }
// response
{ "reranked_queue": [1438, 8592, 2316], "session_confidence": 0.2, "applied": true }
```

### `GET /search?q={query}&type={movie|tv|all}`
Debounced autocomplete backed by the local SQLite index (substring + fuzzy fallback), with optional live TMDB enrichment when a key is set.

### `GET /health`
```json
{ "status": "ok", "model_loaded": true, "index_size": 62000 }
```

---

## Local setup

**Prerequisites:** Python 3.11. No TMDB key and no dataset download are needed
for the quickstart — the API ships with a curated **sample bundle** of ~70
well-known titles and generates its artifacts on first launch.

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
uvicorn main:app --reload      # auto-builds the sample bundle, runs on :8000
```

That's it — three commands. Try it:

```bash
curl localhost:8000/health
curl -X POST localhost:8000/recommend \
  -H 'Content-Type: application/json' \
  -d '{"titles":["Breaking Bad","The Wire"]}'
```

Interactive API docs are at <http://localhost:8000/docs>. The backend also runs
under Docker with `docker compose up`.

### Frontend (the swipe deck)

With the backend running on `:8000`, in a second terminal:

```bash
cd frontend
cp .env.local.example .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev                        # http://localhost:3000
```

Name a few titles you love, then swipe the deck — **→ like, ← pass, ↑ save,
↓ skip** — via touch, mouse drag, the `WASD`/arrow keys, the trackpad (horizontal
like/pass), or the on-screen buttons. The deck quietly re-orders itself after
every swipe as it learns your taste. `npm run build` produces the static export
for Vercel.

### Training on the real MovieLens 25M data (optional)

The sample bundle exists so the project runs instantly; the real pipeline is
fully implemented. To build the production model you need a free
[TMDB API key](https://www.themoviedb.org/settings/api):

```bash
cd backend
pip install -r requirements-train.txt    # heavy stack: surprise, sentence-transformers
cp ../.env.example .env                   # add your TMDB_API_KEY
../scripts/train.sh 0.1                    # download → preprocess (10% sample) → train SVD
# ../scripts/train.sh                      # full 25M run (the production model)
```

`train.sh` runs `data.download` → `data.preprocess` → `ml.collaborative` and
writes the same four artifact files the sample path produces, so the API serves
them with no code change. Set `AUTO_SAMPLE=false` to require real artifacts.

---

## Tests

```bash
cd backend
pytest                 # 14 tests, ~1s
pytest --cov=routers   # routes at 100% line coverage
```

The suite runs entirely on the sample bundle — no download, no TMDB key, no
torch — and exercises the real startup path (artifact generation → model load →
DB seed) via FastAPI's `TestClient`.

---

## Deployment

**Frontend → Vercel**  
Connect repo. Set `NEXT_PUBLIC_API_URL` to your Render backend URL. Push to `main`. Done.

**Backend → Render**  
`render.yaml` is included. Free tier works for demos; precomputed artifacts are committed to the repo (LFS if >100 MB). Set `TMDB_API_KEY` in the Render environment dashboard.

---

## Data sources + licenses

| Source | License | URL |
|---|---|---|
| MovieLens 25M | GroupLens public, non-commercial research | grouplens.org |
| TMDB | CC BY-NC 4.0 for derived data; API free tier | themoviedb.org |
| IMDb title.basics | Free, non-commercial use | imdbws.com |

This project is a portfolio demonstration. It is not for commercial use.

---

## Roadmap

- [x] Phase 1 — Core ML pipeline + API (backend complete, fully tested)
- [x] Phase 2 — Frontend swipe deck + adaptive re-ranking (Layer 1 `/swipe`)
- [ ] Phase 3 — User accounts, saved history, cross-session taste profiles (Layer 2)
- [ ] Phase 4 — Gamification (Daily Pick, streaks, fingerprint) + offline retraining on swipe logs (Layer 3, ALS)
- [ ] Phase 5 — Social: share taste profile, compare with friends

---

## Stack

![Next.js](https://img.shields.io/badge/Next.js_14-black?logo=next.js)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.11-3776AB?logo=python&logoColor=white)
![Tailwind](https://img.shields.io/badge/Tailwind_CSS-06B6D4?logo=tailwindcss&logoColor=white)

---

Built by [Aidan Colvin](https://github.com/aidancolvin) · UNC Chapel Hill CHIP MPS '27