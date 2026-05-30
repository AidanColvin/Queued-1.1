# NextWatch — Product & Build Prompt

Use this as the single source of truth when building, extending, or reviewing
NextWatch. Any change must keep every guarantee below true. The bar: a FAANG
recruiter opens the repo and the app, and within seconds sees a product that is
**modular, intuitive, responsive, and genuinely well-designed** — not generated.

---

## 1. What it is

A Tinder-style **movie & TV recommender**. The landing page *is* the swipe deck —
no search step. The user swipes through full-bleed posters; the engine learns
their taste as they go and refills the deck endlessly.

## 2. Non-negotiable principles

- **Modular.** Small, single-purpose modules with a clear contract between them.
  Backend: typed Pydantic schemas as the API contract; routers thin, ML/data
  logic isolated; the same artifact files feed both the sample and real
  pipelines. Frontend: one concern per file (`deck` state, `api` client, each
  component). A new contributor can find and change one thing without touching
  ten others. **Every function has a docstring.**
- **Intuitive & great UX.** Nothing needs explaining. The primary action (swipe)
  works the obvious way; controls are discoverable; state (which stack, how many
  saved) is always visible. Motion is quick and purposeful, never blocking.
- **Great interface.** Designed, not generated: dark charcoal (`#0d0f12`), amber
  accent (`#f5a623`), DM Serif Display + DM Sans. Posters are the hero. Consistent
  spacing, consistent button sizes, real imagery.
- **Responsive — desktop AND mobile.** Everything fits the visible viewport
  (`100dvh`) with no page scroll; controls stay reachable on a 360px phone and
  scale up cleanly on desktop. Verify both before calling anything done.
- **Resilient.** No dead-ends, no stuck states, no dropped inputs. Network/data
  failures degrade gracefully (fallbacks, never a blank screen).
- **Accessible.** Real `<button>`s, `aria-label`s, keyboard parity, ≥44px touch
  targets, visible focus/active states.

## 3. The experience (exact spec)

### Posters
- Show a real poster for **every** movie and TV title. Source them keylessly
  (Wikidata → English Wikipedia `pageimages`, `pilicense=any`); no API key, baked
  into the catalog so the deployed app needs no runtime dependency.
- Each poster card fits its **natural 2:3 proportion**, centered in the available
  space — never stretched or awkwardly cropped to fill a full-height box.

### Two stacks: Movies and TV
- Top-left: three equal-size pill buttons — **`Movies`** · **`TV`** · **`♡ Watchlist`** —
  slightly larger than the on-card buttons. The active stack is highlighted (amber).
- `Movies` and `TV` are **separate decks**; tapping one jumps to that stack and
  starts it fresh (the shared watchlist is preserved).
- `Watchlist` opens the saved-list drawer (with a count).

### On each card (top-right overlay, equal-size buttons)
- **`♡ Watchlist`** (left) — saves the current title to the watchlist (same as an
  up-swipe).
- **`▶ Trailer`** (right) — opens the trailer.
- No "Film/TV" type badge — the active stack already conveys that.

### Swipe interactions — all four directions, every input method
The deck must respond identically to **keyboard (WASD + arrows), trackpad,
mobile touch-swipe, and the on-screen buttons**:

| Direction | Meaning | Effect |
|-----------|---------|--------|
| **→ right** | Like | record positive signal; recommendations adapt |
| **← left**  | Pass / dislike | record negative signal; show the next |
| **↓ down**  | Haven't seen it / no opinion | skip, no strong signal |
| **↑ up**    | Want to see it | **save to the Watchlist** |

Swiping must feel **immediate** — never lock input for the length of an
animation. Rapid consecutive swipes all register; the deck advances at once and
the outgoing card clears with a fast (~0.2s) transition.

### Watchlist
- Up-swipe or the card's `♡ Watchlist` button adds the title.
- Holds both movies and TV; **persists across reloads** (localStorage, written
  only after restore so it can't be clobbered — guard with state, not a ref,
  because React Strict Mode double-invokes effects).
- Reachable any time via the top-left `Watchlist` button.

## 4. Architecture & data

- **Backend:** FastAPI. `GET /popular`, `POST /recommend` (movies, ML-personalized),
  `GET /tv` (popularity-ranked TV catalog), `POST /swipe` (adaptive re-rank),
  `GET /search`, `GET /health`. Pydantic schemas are the contract; one router per
  concern; tests for every route.
- **Model:** hybrid recommender (collaborative + content + semantic) trained on
  MovieLens-25M — **movies only**. TV is a separate keyless catalog with no ML
  yet (popularity order); only movie titles may seed `/recommend` (TV titles 422
  it), with a `/popular` fallback so the deck never errors.
- **Frontend:** Next.js (App Router, TS strict, Tailwind, framer-motion), static
  export. `lib/deck.ts` owns deck/watchlist state; `lib/api.ts` is the typed
  client; components are presentational.

## 5. Quality gates (before "done")

1. `npm run build` + `tsc --noEmit` clean; backend `pytest` green (every route).
2. Verified **in a real browser at both desktop and mobile widths**: posters
   render in 2:3; both stacks load and switch; all four swipe directions work via
   keys/trackpad/touch/buttons; rapid swipes are never dropped; watchlist saves,
   shows posters, and survives reload; no console errors or failed requests.
3. No secret/key committed; `.env*.local` and build output gitignored.
4. Honest README/status — don't mark phases done that aren't.
