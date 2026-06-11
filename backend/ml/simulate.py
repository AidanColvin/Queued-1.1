"""Batch swipe-simulation harness: many users, many tastes, per-swipe debug.

Answers, with the EXACT production scoring (tuned hybrid space + popularity
prior, the same code paths ``/swipe`` and ``/recommend/adaptive`` run):

    *after each individual swipe, how does the engine's choice of the next
    card — and the next 20 cards — change, and how likely is the user to
    actually like them?*

Two modes:

* ``--personas`` — six synthetic viewers with very different tastes (animation
  family, horror fan, rom-com, ...) swipe through a live deck. After every
  swipe it prints the new top-1 / top-20, each card's calibrated P(like), how
  many of the top-20 fit the persona, and how much the deck shifted.

* ``--users N`` — N real MovieLens users (their actual rating history as
  ground truth). Each user's earliest ratings are replayed as swipes one at a
  time; after every swipe the user's held-out future ratings are re-scored and
  the learning curve P@1 / P@20 / AUC is aggregated across users.

Scores are mapped to probabilities by an empirical calibration: P(like | score)
measured on a held-out MovieLens sample (quantile bins + interpolation), so
"P(like)=0.86" means "historically, 86% of titles scored here were liked".

Run from ``backend`` (inside .venv):
    python -m ml.simulate --personas
    python -m ml.simulate --users 300
Read-only: loads committed artifacts + ratings, touches no database.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ml.artifacts import MovieRecord
from ml.reranker import POP_BETA, SessionReranker, build_taste_space, popularity_prior
from scipy.stats import rankdata

ARTIFACTS = Path("data/artifacts")
LIKE_AT, DISLIKE_AT = 4.0, 2.0
NEUTRAL_MS = 3000
DECK_SIZE = 20
CONFIDENCE_GATE = 0.1  # matches routers.adaptive.ADAPTIVE_MIN_CONFIDENCE


# --------------------------------------------------------------------------- #
# Shared engine state
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Engine:
    """The production ranking state: taste space, prior, catalog maps."""

    catalog: list[MovieRecord]
    space: np.ndarray
    prior: np.ndarray
    movieid_to_idx: dict[int, int]
    calib_x: np.ndarray  # score grid
    calib_y: np.ndarray  # empirical P(like) per grid point

    def prob(self, scores: np.ndarray | float) -> np.ndarray | float:
        """Calibrated P(like) for blended scores."""
        return np.interp(scores, self.calib_x, self.calib_y)

    def blended(self, vector: np.ndarray) -> np.ndarray:
        """Production blended score for the whole catalog (cosine + prior)."""
        norm = float(np.linalg.norm(vector))
        if norm == 0.0:
            return POP_BETA * self.prior.astype(np.float64)
        return self.space @ (vector / norm) + POP_BETA * self.prior

    def rank(self, vector: np.ndarray, confidence: float, exclude: set[int]) -> list[int]:
        """Next-deck catalog idxs, exactly as /recommend/adaptive would pick.

        Below the confidence gate this is the cold-start popularity deck (the
        catalog is ordered most-rated-first); past it, taste-vector candidates.
        """
        if confidence < CONFIDENCE_GATE:
            return [r.idx for r in self.catalog if r.idx not in exclude]
        order = np.argsort(self.blended(vector))[::-1]
        return [int(i) for i in order if int(i) not in exclude]


def _load_engine(n_calib_users: int = 400, seed: int = 0) -> tuple[Engine, "object"]:
    """Build the production-config engine + the raw ratings (lazy import pandas)."""
    import pandas as pd

    movies = json.loads((ARTIFACTS / "movie_index.json").read_text())["movies"]
    catalog = [MovieRecord.from_json(m) for m in movies]
    emb = np.load(ARTIFACTS / "embeddings.npy").astype(np.float32)
    cf = np.load(ARTIFACTS / "cf_item_factors.npy").astype(np.float32)
    space = build_taste_space(emb, cf)  # tuned production default
    prior = popularity_prior(catalog)
    movieid_to_idx = {r.movie_id: r.idx for r in catalog}

    ratings = pd.read_parquet(ARTIFACTS / "ratings.parquet")
    ratings = ratings[ratings["movieId"].isin(movieid_to_idx)]

    calib_x, calib_y = _calibrate(space, prior, movieid_to_idx, ratings, n_calib_users, seed)
    return Engine(catalog, space, prior, movieid_to_idx, calib_x, calib_y), ratings


def _calibrate(space, prior, movieid_to_idx, ratings, n_users: int, seed: int):
    """Empirical P(like | blended score) from a held-out MovieLens sample.

    Quantile-binned like-rates over pooled (score, label) pairs — the same
    temporal 70/30 protocol ``ml.evaluate`` uses, so the probabilities read
    out in the debug logs mean exactly "fraction of similarly-scored titles
    that were actually liked".
    """
    rng = np.random.default_rng(seed)
    counts = ratings.groupby("userId").size()
    users = counts[counts >= 15].index.to_numpy()
    users = rng.choice(users, size=min(n_users, len(users)), replace=False)
    sample = ratings[ratings["userId"].isin(users)].sort_values(["userId", "timestamp"])

    scores, labels = [], []
    for _uid, grp in sample.groupby("userId", sort=False):
        rows = grp.to_dict("records")
        cut = int(len(rows) * 0.7)
        rr = SessionReranker(space, movieid_to_idx, prior=prior)
        for r in rows[:cut]:
            act = "liked" if r["rating"] >= LIKE_AT else "dismissed" if r["rating"] <= DISLIKE_AT else None
            if act:
                rr.update(r["movieId"], act, NEUTRAL_MS)
        norm = float(np.linalg.norm(rr.session_vector))
        if norm == 0.0:
            continue
        unit = rr.session_vector / norm
        for r in rows[cut:]:
            if r["rating"] >= LIKE_AT or r["rating"] <= DISLIKE_AT:
                idx = movieid_to_idx[r["movieId"]]
                scores.append(float(space[idx] @ unit + POP_BETA * prior[idx]))
                labels.append(1 if r["rating"] >= LIKE_AT else 0)

    s, l = np.array(scores), np.array(labels, dtype=np.float64)
    edges = np.quantile(s, np.linspace(0, 1, 21))
    centers, rates = [], []
    for lo, hi in zip(edges, edges[1:]):
        mask = (s >= lo) & (s <= hi)
        if mask.sum() >= 30:
            centers.append(float(s[mask].mean()))
            rates.append(float(l[mask].mean()))
    return np.array(centers), np.array(rates)


# --------------------------------------------------------------------------- #
# Mode 1: synthetic personas, verbose per-swipe debug
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class Persona:
    name: str
    loves: frozenset[str]
    hates: frozenset[str]


PERSONAS = [
    Persona("animation-family", frozenset({"Animation", "Children"}), frozenset({"Horror", "Crime"})),
    Persona("horror-thriller", frozenset({"Horror", "Thriller"}), frozenset({"Children", "Musical"})),
    Persona("scifi-action", frozenset({"Sci-Fi", "Action"}), frozenset({"Romance", "Musical"})),
    Persona("rom-com", frozenset({"Romance", "Comedy"}), frozenset({"Horror", "War"})),
    Persona("prestige-crime", frozenset({"Crime", "Drama", "Film-Noir"}), frozenset({"Children", "Animation"})),
    Persona("war-western", frozenset({"War", "Western"}), frozenset({"Musical", "Children"})),
]


def _decide(persona: Persona, rec: MovieRecord, rng: np.random.Generator, noise: float) -> str:
    """The persona's ground-truth reaction to a card (with optional noise)."""
    g = set(rec.genres)
    fits, clashes = bool(g & persona.loves), bool(g & persona.hates)
    if fits and not clashes:
        action = "liked"
    elif clashes and not fits:
        action = "dismissed"
    else:
        return "skip"  # ambiguous / unfamiliar -> neutral, like production's "not seen"
    if noise and rng.random() < noise:
        action = "dismissed" if action == "liked" else "liked"
    return action


def _fits(persona: Persona, rec: MovieRecord) -> bool:
    g = set(rec.genres)
    return bool(g & persona.loves) and not g & persona.hates


def run_personas(engine: Engine, swipes: int, noise: float, seed: int) -> dict[str, list[float]]:
    """Simulate every persona; print per-swipe debug; return fit-curves."""
    curves: dict[str, list[float]] = {}
    for persona in PERSONAS:
        rng = np.random.default_rng(seed)
        rr = SessionReranker(engine.space, {r.tmdb_id: r.idx for r in engine.catalog if r.tmdb_id}, prior=engine.prior)
        vector, confidence = rr.session_vector, 0.0
        swiped: set[int] = set()
        curve: list[float] = []

        deck = engine.rank(vector, confidence, swiped)[:DECK_SIZE]
        fit0 = sum(_fits(persona, engine.catalog[i]) for i in deck)
        print(f"\n=== {persona.name}  (loves {set(persona.loves)}, hates {set(persona.hates)}) ===")
        print(f"  cold-start deck: {fit0}/{DECK_SIZE} cards fit this taste")
        curve.append(fit0 / DECK_SIZE)

        for n in range(1, swipes + 1):
            top = engine.catalog[deck[0]]
            action = _decide(persona, top, rng, noise)
            swiped.add(top.idx)
            weight = {"liked": 1.0, "dismissed": -0.55}.get(action, 0.0)
            if weight:
                vector = vector + weight * engine.space[top.idx]
                confidence = min(confidence + abs(weight) * 0.1, 1.0)

            prev_deck = deck
            deck = engine.rank(vector, confidence, swiped)[:DECK_SIZE]
            probs = engine.prob(engine.blended(vector)[deck]) if confidence >= CONFIDENCE_GATE else None
            fit = sum(_fits(persona, engine.catalog[i]) for i in deck)
            curve.append(fit / DECK_SIZE)
            entrants = len(set(deck) - set(prev_deck))
            nxt = engine.catalog[deck[0]]

            mark = {"liked": "LIKE   ", "dismissed": "DISLIKE", "skip": "skip   "}[action]
            p1 = f"P(like)={probs[0]:.2f}" if probs is not None else "P(like)=n/a (cold)"
            p20 = f"mean P={probs.mean():.2f}" if probs is not None else "popularity order"
            print(
                f"  #{n:02d} {mark} {top.title[:34]:<34} -> next-1: {nxt.title[:30]:<30} {p1}"
                f" | next-20: {fit:>2}/20 fit, {p20}, {entrants:>2} new"
            )
        curves[persona.name] = curve
        print(f"  learning curve (top-20 taste-fit): {fit0}/{DECK_SIZE} cold -> {fit}/{DECK_SIZE} after {swipes} swipes")
    return curves


# --------------------------------------------------------------------------- #
# Mode 2: batch over real MovieLens users — learning curve per swipe
# --------------------------------------------------------------------------- #
def _auc(scores: np.ndarray, labels: np.ndarray) -> float:
    pos = labels == 1
    n_pos, n_neg = int(pos.sum()), int((~pos).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = rankdata(scores)
    return (ranks[pos].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def run_batch(engine: Engine, ratings, n_users: int, max_swipes: int, seed: int) -> list[dict]:
    """Replay real users' histories swipe-by-swipe; aggregate the learning curve.

    For each user: their first ``max_swipes`` judged ratings (time order) are
    the swipes; everything after is the holdout. After swipe k the holdout is
    re-scored with the production blend and we record whether the #1 pick (and
    the top-20) would actually have been liked.
    """
    rng = np.random.default_rng(seed)
    counts = ratings.groupby("userId").size()
    users = counts[counts >= max_swipes + 40].index.to_numpy()
    users = rng.choice(users, size=min(n_users, len(users)), replace=False)
    sample = ratings[ratings["userId"].isin(users)].sort_values(["userId", "timestamp"])

    # per swipe-count k: pooled P@1 hits, P@20 rates, per-user AUCs, top-1 probs
    agg = [{"p1": [], "p20": [], "auc": [], "prob1": []} for _ in range(max_swipes + 1)]
    n_used = 0

    for _uid, grp in sample.groupby("userId", sort=False):
        judged = [
            (engine.movieid_to_idx[r["movieId"]], 1 if r["rating"] >= LIKE_AT else 0)
            for r in grp.to_dict("records")
            if r["rating"] >= LIKE_AT or r["rating"] <= DISLIKE_AT
        ]
        if len(judged) < max_swipes + 25:
            continue
        train, held = judged[:max_swipes], judged[max_swipes:]
        held_idx = np.array([i for i, _ in held])
        held_lab = np.array([lab for _, lab in held])
        if held_lab.sum() in (0, held_lab.size):
            continue  # need both classes held out for AUC
        n_used += 1

        vector = np.zeros(engine.space.shape[1], dtype=np.float32)
        for k in range(max_swipes + 1):
            scores = (
                engine.space[held_idx] @ (vector / np.linalg.norm(vector)) + POP_BETA * engine.prior[held_idx]
                if np.linalg.norm(vector) > 0
                else POP_BETA * engine.prior[held_idx].astype(np.float64)
            )
            order = np.argsort(-scores)
            agg[k]["p1"].append(float(held_lab[order[0]]))
            agg[k]["p20"].append(float(held_lab[order[:20]].mean()))
            agg[k]["auc"].append(_auc(scores, held_lab))
            agg[k]["prob1"].append(float(engine.prob(scores[order[0]])))
            if k < max_swipes:
                idx, lab = train[k]
                vector = vector + (1.0 if lab else -0.55) * engine.space[idx]

    base = float(np.mean([np.mean(a["p20"]) for a in agg[:1]]))  # k=0 row exists below
    print(f"\n=== batch: {n_used} real users, judged-holdout learning curve ===")
    print(f"{'swipes':>6} {'P@1':>7} {'P@20':>7} {'AUC':>7} {'est.P(top-1)':>13}   Δ P@20 vs cold")
    rows = []
    for k, a in enumerate(agg):
        p1, p20 = float(np.mean(a["p1"])), float(np.mean(a["p20"]))
        auc = float(np.nanmean(a["auc"]))
        pr = float(np.mean(a["prob1"]))
        rows.append({"swipes": k, "p@1": p1, "p@20": p20, "auc": auc, "prob_top1": pr})
        delta = p20 - rows[0]["p@20"]
        print(f"{k:>6} {p1:>7.3f} {p20:>7.3f} {auc:>7.3f} {pr:>13.2f}   {delta:+.3f}")
    _ = base
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description="Batch swipe simulation with per-swipe debug.")
    ap.add_argument("--personas", action="store_true", help="verbose per-swipe persona debug")
    ap.add_argument("--users", type=int, default=0, help="batch over N real MovieLens users")
    ap.add_argument("--swipes", type=int, default=15, help="swipes per simulated session")
    ap.add_argument("--noise", type=float, default=0.1, help="persona decision noise rate")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    if not args.personas and not args.users:
        args.personas, args.users = True, 300  # default: both modes

    print("Loading artifacts + calibrating P(like|score) on a MovieLens holdout...")
    engine, ratings = _load_engine(seed=args.seed)
    print(f"  calibration: score {engine.calib_x[0]:.2f} -> P(like) {engine.calib_y[0]:.2f}"
          f" ... score {engine.calib_x[-1]:.2f} -> P(like) {engine.calib_y[-1]:.2f}")

    if args.personas:
        run_personas(engine, args.swipes, args.noise, args.seed)
    if args.users:
        run_batch(engine, ratings, args.users, args.swipes, args.seed)


if __name__ == "__main__":
    main()
