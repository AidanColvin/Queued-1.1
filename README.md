# Queued

[![CI](https://github.com/AidanColvin/nextwatch/actions/workflows/ci.yml/badge.svg)](https://github.com/AidanColvin/nextwatch/actions/workflows/ci.yml)

**AI-powered movie and TV recommendation engine.**  
Input titles you have loved. Get ranked suggestions from a hybrid ML pipeline trained on 25 million public ratings.

> Live demo → `queued-2.vercel.app` · Backend → Render free tier

---

## What it does

You give Queued a list of movies or shows. It analyzes your taste across three axes — collaborative signal (what similar viewers watched), content signal (genre and tag overlap), and semantic signal (plot embedding similarity) — blends them into a single ranked list, and tells you *why* each title was recommended.

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
The model trains on a stack of public datasets, no single one carrying the whole signal:

| Source | License | Role in the pipeline |
|---|---|---|
| [MovieLens 25M](https://grouplens.org/datasets/movielens/25m/) | GroupLens, non-commercial | 25M ratings → collaborative filtering; **genome-scores** (1,128 tag-relevance scores/movie) → richest content signal |
| [CMU Movie Summary Corpus](http://www.cs.cmu.edu/~ark/personas/data/) | free, research | 42K plot summaries → semantic embedding text (no API key) |
| [IMDb TSV dumps](https://datasets.imdbws.com/) | free, non-commercial | canonical titles + years |
| [TMDB API](https://www.themoviedb.org/documentation/api) | free tier | posters, cast, overview (optional — layered on after training) |

Because the semantic and content signals come from CMU + genome (not TMDB), the model **trains fully without a TMDB key**; TMDB is only needed for posters.

### Models
**Collaborative filtering** (truncated SVD of the user-item matrix, `scikit-learn`). Learns latent item factors from 25M ratings. Given seed movies, averages their item vectors and cosine-ranks all others against that mean — capturing behavioral patterns genre labels miss, e.g. "prestige TV with unreliable narrators." (scikit-learn's SVD is used over scikit-surprise's, which is incompatible with NumPy 2.)

**Content-based filtering** (TF-IDF cosine similarity). A sparse matrix over genres, user tags, and the top **genome tags** per movie — the densest metadata signal in the dataset. Handles cold-start: new titles still surface when their metadata overlaps.

**Semantic similarity** (sentence-transformers `all-MiniLM-L6-v2`). Encodes **CMU plot summaries** into 384-dim vectors, finding thematically related titles even when genres diverge. Runs at inference against precomputed embeddings.

### Hybrid blending
```python
score = 0.45 * cf_score + 0.35 * content_score + 0.20 * semantic_score
```
Weights were tuned empirically on a held-out 20% of the MovieLens test split. CF dominates because behavioral signal is the strongest predictor at this dataset scale. Semantic score adds diversity — prevents the list from collapsing to a single genre.

### Adaptive re-ranking (learns as you swipe)

The model never cold-starts against *you* — it ships trained on 25M ratings, so the first card is already good. From there it personalizes in real time. Each swipe nudges a per-session preference vector toward (or away from) the card's embedding, and the remaining deck is re-sorted by cosine similarity — pure numpy, ~milliseconds, **no retraining** ([`ml/reranker.py`](backend/ml/reranker.py)):

```python
SIGNAL_WEIGHTS = {"liked": 1.0, "saved": 0.65, "skip": 0.0, "dismissed": -0.55}
```

The four directions map to **like** (→), **dislike** (←), **watchlist / save** (↑) and **"haven't seen it"** (↓). The signals are deliberately **asymmetric** — a dislike is not the mirror of a like — and a `time_on_card_ms` modifier treats a fast dislike as a confident "no" and a long hesitation as a soft "maybe". "Haven't seen it" is weighted **neutral**: it signals unfamiliarity, not taste, so a discovery app must not learn *away* from titles you simply haven't met — but it is still logged. Every swipe is written to `swipe_events` as the source of truth for periodic offline retraining (planned: ALS on implicit feedback). Cross-session user profiles arrive with accounts in Phase 3.

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

### Training on the real MovieLens 25M data

The sample bundle exists so the project runs instantly, but the real pipeline is
what produces the production model — and it **needs no API key** (CMU summaries
and genome-scores carry the semantic + content signal; TMDB is only for posters):

```bash
cd backend
pip install -r requirements-train.txt    # pandas, scikit-learn, sentence-transformers
../scripts/train.sh 0.1                    # download → preprocess (10% sample) → train SVD
# ../scripts/train.sh                      # full 25M run (the production model)
```

`train.sh` runs `data.download` → `data.preprocess` → `ml.collaborative` and
writes the same four artifact files the sample produces, so the API serves them
with no code change. A 10% sample yields ~5,400 movies (a genuinely endless
deck); the recommendations are real — e.g. *Pulp Fiction → Reservoir Dogs,
Kill Bill, Jackie Brown*.

**Posters + accurate cast** then come from a free
[TMDB key](https://www.themoviedb.org/settings/api):

```bash
echo "TMDB_API_KEY=..." >> .env
python -m data.enrich_sample   # backfills posters + cast into the bundle
```

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
`render.yaml` is included and now provisions a **Render Postgres** instance
(`queued-db`) wired into `DATABASE_URL`, with `alembic upgrade head` run as
the pre-deploy step so the schema migrates before each release goes live. Free
tier works for demos; precomputed artifacts are committed to the repo (LFS if
>100 MB). Set `TMDB_API_KEY` and `JWT_SECRET` in the Render environment
dashboard. SQLite remains the zero-setup default for local dev and tests.

Production hardening that ships with the backend:

- **Durable re-ranking** — anonymous session taste vectors persist to
  `anon_session_profiles`, so the live deck re-ranking survives restarts and
  multi-instance deployments (signed-in users already persisted via
  `user_profiles`).
- **Password reset + email verification** — token-based (purpose-scoped JWTs),
  emailed over SMTP when `EMAIL_HOST` is set, logged to the console in dev.
- **Rate limiting** — per-IP sliding windows on all auth endpoints.
- **CORS locked down** — explicit origins only (SPA + Capacitor shell).
- **Account deletion** — `DELETE /account` removes the user and every row tied
  to them (required for App Store distribution), with a confirm UI in the
  account menu.

---

## Data sources + licenses

| Source | License | URL |
|---|---|---|
| MovieLens 25M | GroupLens public, non-commercial research | grouplens.org |
| TMDB | CC BY-NC 4.0 for derived data; API free tier | themoviedb.org |
| IMDb title.basics | Free, non-commercial use | imdbws.com |

This project is a portfolio demonstration. It is not for commercial use.

---

## Streaming services (onboarding + deck filter)

New accounts see a one-time onboarding screen ("Where do you watch?") with
tappable buttons for Netflix, Hulu, Max, Disney+, Prime Video, Apple TV+,
Paramount+ and Peacock; the selection is editable later from the account menu
and guests can set it too (localStorage, merged on sign-up). The deck then
offers a three-state filter — **All titles / My services (hard filter) / Boost
mine (soft re-rank)** — applied server-side in `/recommend`, `/popular`, `/tv`
and the `/swipe` re-ranker, with provider chips rendered on each card.

Per-title availability comes from TMDB's `watch/providers` endpoint (data by
**JustWatch** — attribution rendered in the UI):

```bash
cd backend
TMDB_API_KEY=... python -m data.enrich_providers            # fill gaps
TMDB_API_KEY=... python -m data.enrich_providers --refresh  # nightly re-sync
```

This writes `data/artifacts/providers.json`, which the API loads at startup
(and mirrors into the `title_providers` table). Until it exists, the filter
gracefully degrades to "All titles".

---

## Letterboxd import

Connect a Letterboxd account from the account menu — no API key required:

- **RSS sync** — enter a username and Queued reads the public diary feed
  (`letterboxd.com/{user}/rss/`, the ~50 most recent entries).
- **Export upload** — upload the Letterboxd data-export ZIP (or a bare
  `ratings.csv` / `watched.csv`) for full history.

Films are matched by TMDB id, then by normalized title + year (±1). Ratings of
**≥ 3.5★ become liked seeds**, everything watched joins the seen-set (so it
stops appearing in the deck), and new likes immediately nudge the persisted
taste vector. Imports are idempotent — re-syncing never duplicates anything —
and unmatched titles are kept in `external_ratings` for review.

---

## The "For You" page

`GET /recommendations/personal` builds ranked shelves from **everything known
about the caller** — saved likes, the swipe log, imported Letterboxd ratings:

- *Because you liked &lt;title&gt;* — hybrid ranking, one shelf per top seed
- *Loved by viewers like you* — pure collaborative (SVD) signal
- *On your services* — hard-filtered to the user's streaming services

Seen titles never reappear and no title repeats across shelves. Anonymous
visitors get the same shelves from their session's likes plus a sign-in nudge
(falling back to the popular deck with no signal at all). Reachable from the
**✦ For You** button on the deck.

---

## Roadmap

- [x] Phase 1 — Core ML pipeline + API (backend complete, fully tested)
- [x] Phase 2 — Frontend swipe deck + adaptive re-ranking (Layer 1 `/swipe`)
- [ ] Phase 3 — User accounts, saved history, cross-session taste profiles (Layer 2)
- [x] Phase 3 (accounts) shipped, plus: production hardening (Postgres/Alembic,
      durable sessions, password reset/email verification, rate limiting,
      account deletion), streaming-service onboarding + deck filters,
      Letterboxd import, the For You page, and iOS packaging via Capacitor
      (see [docs/APP_STORE.md](docs/APP_STORE.md))
- [ ] Gamification (Daily Pick, streaks, fingerprint) + offline retraining on swipe logs (Layer 3, ALS)
- [ ] Social: share taste profile, compare with friends

## iOS app (Capacitor)

The same static export ships as a native iOS app: `npm run build:native` in
`frontend/` builds the bundle and syncs it into the checked-in Xcode project
(`frontend/ios/`). Native builds authenticate with a bearer token in Capacitor
Preferences, add Sign in with Apple (`POST /auth/apple`, JWKS-verified) and
real swipe haptics. The full Apple-side checklist — certificates, TestFlight,
App Privacy, and the **MovieLens non-commercial licensing constraint** — lives
in [docs/APP_STORE.md](docs/APP_STORE.md).

---

## Stack

![Next.js](https://img.shields.io/badge/Next.js_14-black?logo=next.js)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.11-3776AB?logo=python&logoColor=white)
![Tailwind](https://img.shields.io/badge/Tailwind_CSS-06B6D4?logo=tailwindcss&logoColor=white)

---

Built by [Aidan Colvin](https://github.com/aidancolvin) · UNC Chapel Hill CHIP MPS '27