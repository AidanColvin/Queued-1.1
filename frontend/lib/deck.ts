// Endless deck state. Cards are appended as the backend supplies more, never
// removed (the cursor just advances), so the queue doubles as the "already
// shown" set used to exclude repeats. Liked + wish-list cards persist to
// localStorage so they survive a refresh.

'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { CardDecision, Recommendation, SwipeAction } from './types';

interface DeckState {
  queue: Recommendation[];
  current: number;
  decisions: CardDecision[];
  likedCards: Recommendation[];
  wishlistCards: Recommendation[];
}

export interface DeckApi {
  currentCard: Recommendation | null;
  upcoming: Recommendation[];
  upcomingCount: number;
  decisionsCount: number;
  liked: Recommendation[];
  wishlist: Recommendation[];
  /** Every TMDB id ever queued — pass to the backend to avoid repeats. */
  knownIds: number[];
  /** Recent positive titles (liked + wish-listed), used to seed adaptive refills. */
  positiveTitles: string[];
  canUndo: boolean;
  commit: (action: SwipeAction) => { card: Recommendation; remaining: number[] } | null;
  undo: () => void;
  reorderRemaining: (ids: number[]) => void;
  /** Append fresh cards, skipping any already in the deck. Returns # added. */
  append: (recs: Recommendation[]) => number;
  /** Empty the queue + history for a fresh stack; keeps liked + wish list. */
  reset: () => void;
}

const LIKED_KEY = 'nextwatch:liked';
const WISHLIST_KEY = 'nextwatch:wishlist';

function load(key: string): Recommendation[] {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as Recommendation[]) : [];
  } catch {
    return [];
  }
}

export function useDeck(): DeckApi {
  const [state, setState] = useState<DeckState>(() => ({
    queue: [],
    current: 0,
    decisions: [],
    likedCards: [],
    wishlistCards: [],
  }));
  const stateRef = useRef(state);
  stateRef.current = state;
  // Gates persistence: stays false until the restore below has committed, so we
  // never write the empty initial state over saved items. It must be state (not
  // a ref) so React Strict Mode's double-invoked effects can't flip it early.
  const [hydrated, setHydrated] = useState(false);

  // Restore persisted wish list + likes once on mount. Client-only, so SSR and
  // first paint both render the empty initial state and never mismatch.
  useEffect(() => {
    setState((s) => ({ ...s, likedCards: load(LIKED_KEY), wishlistCards: load(WISHLIST_KEY) }));
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return; // don't persist until the restore has run
    try {
      localStorage.setItem(LIKED_KEY, JSON.stringify(state.likedCards));
      localStorage.setItem(WISHLIST_KEY, JSON.stringify(state.wishlistCards));
    } catch {
      /* storage unavailable — non-fatal */
    }
  }, [hydrated, state.likedCards, state.wishlistCards]);

  const commit = useCallback<DeckApi['commit']>((action) => {
    const s = stateRef.current;
    const card = s.queue[s.current];
    if (!card) return null;
    const remaining = s.queue
      .slice(s.current + 1)
      .map((r) => r.tmdb_id)
      .filter((id): id is number => id != null);
    const decision: CardDecision = {
      tmdbId: card.tmdb_id ?? -1,
      title: card.title,
      action,
      timestamp: Date.now(),
    };
    setState((prev) => ({
      ...prev,
      current: prev.current + 1,
      decisions: [...prev.decisions, decision],
      likedCards: action === 'liked' ? [...prev.likedCards, card] : prev.likedCards,
      wishlistCards: action === 'saved' ? [...prev.wishlistCards, card] : prev.wishlistCards,
    }));
    return { card, remaining };
  }, []);

  const undo = useCallback(() => {
    setState((s) => {
      if (s.decisions.length === 0) return s;
      const last = s.decisions[s.decisions.length - 1];
      return {
        ...s,
        current: Math.max(0, s.current - 1),
        decisions: s.decisions.slice(0, -1),
        likedCards: last.action === 'liked' ? s.likedCards.slice(0, -1) : s.likedCards,
        wishlistCards: last.action === 'saved' ? s.wishlistCards.slice(0, -1) : s.wishlistCards,
      };
    });
  }, []);

  const reorderRemaining = useCallback((ids: number[]) => {
    setState((s) => {
      const head = s.queue.slice(0, s.current);
      const tail = s.queue.slice(s.current);
      const byId = new Map<number, Recommendation>();
      for (const r of tail) if (r.tmdb_id != null) byId.set(r.tmdb_id, r);
      const ordered: Recommendation[] = [];
      for (const id of ids) {
        const r = byId.get(id);
        if (r) {
          ordered.push(r);
          byId.delete(id);
        }
      }
      for (const r of tail) if (r.tmdb_id == null || byId.has(r.tmdb_id)) ordered.push(r);
      return { ...s, queue: [...head, ...ordered] };
    });
  }, []);

  const reset = useCallback(() => {
    setState((s) => ({ ...s, queue: [], current: 0, decisions: [] }));
  }, []);

  const append = useCallback<DeckApi['append']>((recs) => {
    let added = 0;
    setState((s) => {
      // De-duplicate on the stable `id` (movie_id) — tmdb_id can be null for
      // some real titles, which previously let them recirculate.
      const known = new Set(s.queue.map((r) => r.id));
      const fresh = recs.filter((r) => !known.has(r.id));
      added = fresh.length;
      return fresh.length ? { ...s, queue: [...s.queue, ...fresh] } : s;
    });
    return added;
  }, []);

  return useMemo<DeckApi>(() => {
    const knownIds = state.queue.map((r) => r.id);
    return {
      currentCard: state.queue[state.current] ?? null,
      upcoming: state.queue.slice(state.current + 1, state.current + 3),
      upcomingCount: Math.max(0, state.queue.length - state.current - 1),
      decisionsCount: state.decisions.length,
      liked: state.likedCards,
      wishlist: state.wishlistCards,
      knownIds,
      // Movies-only: the recommender can't resolve TV titles, so never seed it
      // with them (doing so 422s the whole request).
      positiveTitles: [
        ...new Set(
          [...state.likedCards, ...state.wishlistCards]
            .filter((r) => r.type === 'movie')
            .map((r) => r.title),
        ),
      ].slice(-8),
      canUndo: state.decisions.length > 0,
      commit,
      undo,
      reorderRemaining,
      append,
      reset,
    };
  }, [state, commit, undo, reorderRemaining, append, reset]);
}
