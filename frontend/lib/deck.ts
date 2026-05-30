// Deck state: queue of cards, decision history (for undo + summary), and silent
// re-ordering of the upcoming cards after each swipe. History persists to
// localStorage so a refresh resumes where the user left off.

'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { CardDecision, Recommendation, SwipeAction } from './types';

interface DeckState {
  queue: Recommendation[];
  current: number;
  decisions: CardDecision[];
}

export interface DeckApi {
  /** The card awaiting a decision, or null when the deck is exhausted. */
  currentCard: Recommendation | null;
  /** Up to two cards peeking behind the current one. */
  upcoming: Recommendation[];
  current: number;
  total: number;
  decisions: CardDecision[];
  liked: Recommendation[];
  saved: Recommendation[];
  isDone: boolean;
  canUndo: boolean;
  /** Record a decision on the current card and advance. Returns the decided
   *  card and the tmdb_ids still pending (to send to /swipe). */
  commit: (action: SwipeAction) => { card: Recommendation; remaining: number[] } | null;
  /** Step back one card. */
  undo: () => void;
  /** Silently re-order the still-pending cards to match `ids`. */
  reorderRemaining: (ids: number[]) => void;
}

const STORAGE_PREFIX = 'nextwatch:deck:';

export function useDeck(recommendations: Recommendation[], key: string): DeckApi {
  const [state, setState] = useState<DeckState>(() => ({
    queue: recommendations,
    current: 0,
    decisions: [],
  }));

  // Mirror of the latest state for synchronous reads inside `commit` (a setState
  // updater is not invoked synchronously, so we cannot rely on it to return).
  const stateRef = useRef(state);
  stateRef.current = state;

  // Re-initialize when a new deck arrives, restoring any saved progress.
  useEffect(() => {
    let decisions: CardDecision[] = [];
    try {
      const raw = localStorage.getItem(STORAGE_PREFIX + key);
      if (raw) decisions = JSON.parse(raw) as CardDecision[];
    } catch {
      /* ignore malformed storage */
    }
    const decidedIds = new Set(decisions.map((d) => d.tmdbId));
    const current = recommendations.filter((r) => r.tmdb_id != null && decidedIds.has(r.tmdb_id)).length;
    setState({ queue: recommendations, current, decisions });
  }, [key, recommendations]);

  // Persist history on every change.
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(state.decisions));
    } catch {
      /* storage full / unavailable — non-fatal */
    }
  }, [key, state.decisions]);

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
    }));
    return { card, remaining };
  }, []);

  const undo = useCallback(() => {
    setState((s) => {
      if (s.decisions.length === 0) return s;
      return {
        ...s,
        current: Math.max(0, s.current - 1),
        decisions: s.decisions.slice(0, -1),
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

  return useMemo<DeckApi>(() => {
    const liked = state.queue.filter((r) =>
      state.decisions.some((d) => d.tmdbId === r.tmdb_id && d.action === 'liked'),
    );
    const saved = state.queue.filter((r) =>
      state.decisions.some((d) => d.tmdbId === r.tmdb_id && d.action === 'saved'),
    );
    return {
      currentCard: state.queue[state.current] ?? null,
      upcoming: state.queue.slice(state.current + 1, state.current + 3),
      current: state.current,
      total: state.queue.length,
      decisions: state.decisions,
      liked,
      saved,
      isDone: state.current >= state.queue.length,
      canUndo: state.decisions.length > 0,
      commit,
      undo,
      reorderRemaining,
    };
  }, [state, commit, undo, reorderRemaining]);
}
