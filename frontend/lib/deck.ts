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
  /** Persisted ids of every card ever shown — survives reloads so the deck
   *  never re-serves a title the user has already seen. */
  seenIds: number[];
}

export interface DeckApi {
  currentCard: Recommendation | null;
  upcoming: Recommendation[];
  upcomingCount: number;
  decisionsCount: number;
  liked: Recommendation[];
  wishlist: Recommendation[];
  /** Every id ever shown — current queue ∪ the persisted seen set. Pass to the
   *  backend as the exclude list so a card is never served twice, even across
   *  page reloads / cold-starts. */
  knownIds: number[];
  /** Recent positive titles (liked + wish-listed), used to seed adaptive refills. */
  positiveTitles: string[];
  /** True once localStorage has been restored — gate the first fetch on this so
   *  the initial deck already excludes everything seen in past sessions. */
  hydrated: boolean;
  canUndo: boolean;
  commit: (action: SwipeAction) => { card: Recommendation; remaining: number[] } | null;
  undo: () => void;
  reorderRemaining: (ids: number[]) => void;
  /** Append fresh cards to the queue, skipping any already in the deck. Pass
   *  `fetchedAll` (the full fetched batch) to mark *every* fetched id as seen —
   *  including ones filtered out (e.g. no poster) — so they never get re-served.
   *  Returns the number of cards actually queued. */
  append: (recs: Recommendation[], fetchedAll?: Recommendation[]) => number;
  /** Empty the queue + history for a fresh stack; keeps liked + wish list. */
  reset: () => void;
}

const LIKED_KEY = 'nextwatch:liked';
const WISHLIST_KEY = 'nextwatch:wishlist';
const SEEN_KEY = 'nextwatch:seen';

function load(key: string): Recommendation[] {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as Recommendation[]) : [];
  } catch {
    return [];
  }
}

/** Restore a persisted id list (the seen set), tolerating absent/corrupt data. */
function loadIds(key: string): number[] {
  try {
    const raw = localStorage.getItem(key);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((n): n is number => typeof n === 'number') : [];
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
    seenIds: [],
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
    setState((s) => ({
      ...s,
      likedCards: load(LIKED_KEY),
      wishlistCards: load(WISHLIST_KEY),
      seenIds: loadIds(SEEN_KEY),
    }));
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return; // don't persist until the restore has run
    try {
      localStorage.setItem(LIKED_KEY, JSON.stringify(state.likedCards));
      localStorage.setItem(WISHLIST_KEY, JSON.stringify(state.wishlistCards));
      localStorage.setItem(SEEN_KEY, JSON.stringify(state.seenIds));
    } catch {
      /* storage unavailable — non-fatal */
    }
  }, [hydrated, state.likedCards, state.wishlistCards, state.seenIds]);

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

  const append = useCallback<DeckApi['append']>((recs, fetchedAll) => {
    const allFetched = fetchedAll ?? recs;
    let added = 0;
    setState((s) => {
      // De-duplicate on the stable `id` (movie_id) against both the current
      // queue AND the persisted seen set, so a title the user already saw in a
      // previous session can never re-enter the deck. (tmdb_id can be null for
      // some real titles, which previously let them recirculate.)
      const known = new Set<number>([...s.queue.map((r) => r.id), ...s.seenIds]);
      const fresh = recs.filter((r) => !known.has(r.id));
      added = fresh.length;
      // Mark every *fetched* id as seen — including titles the caller filtered
      // out (e.g. for having no poster) — so the backend's exclude list skips
      // them next time and they never recirculate.
      const newlySeen = allFetched.map((r) => r.id).filter((id) => !known.has(id));
      if (!fresh.length && !newlySeen.length) return s;
      return {
        ...s,
        queue: [...s.queue, ...fresh],
        seenIds: [...s.seenIds, ...newlySeen],
      };
    });
    return added;
  }, []);

  return useMemo<DeckApi>(() => {
    // Union of the persisted seen set and the current queue — the full exclude
    // list, so refills *and* the cold-start/initial deck both skip seen cards.
    const knownIds = [...new Set<number>([...state.seenIds, ...state.queue.map((r) => r.id)])];
    return {
      currentCard: state.queue[state.current] ?? null,
      upcoming: state.queue.slice(state.current + 1, state.current + 3),
      upcomingCount: Math.max(0, state.queue.length - state.current - 1),
      decisionsCount: state.decisions.length,
      liked: state.likedCards,
      wishlist: state.wishlistCards,
      knownIds,
      hydrated,
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
  }, [state, hydrated, commit, undo, reorderRemaining, append, reset]);
}
