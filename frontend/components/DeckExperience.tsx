'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { getPopular, getRecommendations, getTv } from '@/lib/api';
import { useDeck } from '@/lib/deck';
import type { Recommendation } from '@/lib/types';
import { youtubeTrailerUrl } from '@/lib/util';
import SwipeDeck from './SwipeDeck';
import WishlistDrawer from './WishlistDrawer';

interface DeckExperienceProps {
  /** Optional seed titles (shared links). Empty → popular cold-start deck. */
  seedTitles?: string[];
}

type Stack = 'movie' | 'tv';

const REFILL_AT = 5; // fetch more when this few cards remain
const REFILL_COUNT = 15;

export default function DeckExperience({ seedTitles = [] }: DeckExperienceProps) {
  const deck = useDeck();
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [wishlistOpen, setWishlistOpen] = useState(false);
  const [stack, setStack] = useState<Stack>('movie');
  const fetchingRef = useRef(false);
  const startedRef = useRef(false);
  const exhaustedRef = useRef(false);

  // Pull the next batch for the active stack. Movies are ML-personalized (seeded
  // by what you've liked); TV is a separate popularity-ranked catalog. `initial`
  // requests start from a clean slate so switching stacks never carries excludes.
  const fetchMore = useCallback(
    async (initial: boolean, forStack: Stack) => {
      if (fetchingRef.current) return;
      fetchingRef.current = true;
      try {
        const exclude = initial ? [] : deck.knownIds;
        const count = initial ? 20 : REFILL_COUNT;
        let res;
        if (forStack === 'tv') {
          res = await getTv(count, exclude);
        } else {
          const seeds = deck.positiveTitles.length ? deck.positiveTitles : seedTitles;
          // Adaptive when we have movie seeds; fall back to popular if /recommend
          // can't resolve them (or fails), so the deck never dead-ends.
          res = seeds.length
            ? await getRecommendations(seeds, REFILL_COUNT, exclude).catch(() => getPopular(count, exclude))
            : await getPopular(count, exclude);
        }
        const added = deck.append(res.recommendations);
        if (!initial && added === 0) exhaustedRef.current = true; // catalog drained
        setStatus('ready');
      } catch {
        if (initial) setStatus('error');
      } finally {
        fetchingRef.current = false;
      }
    },
    [deck, seedTitles],
  );

  // Initial load (once).
  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    void fetchMore(true, 'movie');
  }, [fetchMore]);

  // Endless refill: keep the queue topped up as the user swipes.
  useEffect(() => {
    if (status === 'ready' && !exhaustedRef.current && deck.upcomingCount <= REFILL_AT) {
      void fetchMore(false, stack);
    }
  }, [status, deck.upcomingCount, fetchMore, stack]);

  // Jump between the Movies and TV stacks: reset the deck (keeping the shared
  // watchlist) and load the other catalog fresh.
  const switchStack = useCallback(
    (next: Stack) => {
      if (next === stack || fetchingRef.current) return;
      setStack(next);
      exhaustedRef.current = false;
      deck.reset();
      setStatus('loading');
      void fetchMore(true, next);
    },
    [stack, deck, fetchMore],
  );

  const openCard = useCallback((rec: Recommendation) => {
    window.open(youtubeTrailerUrl(rec.title, rec.year), '_blank', 'noopener,noreferrer');
  }, []);

  const navBtn = (active: boolean) =>
    `rounded-full px-3 py-1.5 text-sm font-medium transition ${
      active ? 'bg-amber text-charcoal' : 'border border-warm text-ink hover:border-amber'
    }`;

  return (
    <main className="app-shell mx-auto flex w-full max-w-3xl flex-col px-4 py-3 sm:py-5">
      <header className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <button type="button" onClick={() => switchStack('movie')} className={navBtn(stack === 'movie')}>
            Movies
          </button>
          <button type="button" onClick={() => switchStack('tv')} className={navBtn(stack === 'tv')}>
            TV
          </button>
          <button
            type="button"
            onClick={() => setWishlistOpen(true)}
            className="rounded-full border border-warm px-3 py-1.5 text-sm font-medium text-ink transition hover:border-amber"
          >
            ♡ Watchlist{deck.wishlist.length ? ` ${deck.wishlist.length}` : ''}
          </button>
        </div>
        <span className="hidden text-sm font-semibold uppercase tracking-[0.25em] text-amber/80 sm:inline">
          NextWatch
        </span>
      </header>

      <div className="flex min-h-0 flex-1 flex-col">
        {status === 'loading' && (
          <div className="flex flex-1 items-center justify-center">
            <p className="animate-pulse font-serif text-2xl text-muted">Finding something to watch…</p>
          </div>
        )}

        {status === 'error' && (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
            <p className="text-pass">Couldn&apos;t reach the recommender.</p>
            <button
              type="button"
              onClick={() => {
                setStatus('loading');
                void fetchMore(true, stack);
              }}
              className="rounded-full border border-warm px-5 py-2.5 text-ink transition hover:border-amber"
            >
              Retry
            </button>
          </div>
        )}

        {status === 'ready' &&
          (deck.currentCard ? (
            <SwipeDeck deck={deck} onOpenCard={openCard} />
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
              <p className="font-serif text-2xl text-muted">
                {exhaustedRef.current
                  ? `That's every popular ${stack === 'tv' ? 'show' : 'title'} — nice swiping.`
                  : 'Lining up more picks…'}
              </p>
              {exhaustedRef.current && (
                <button
                  type="button"
                  onClick={() => switchStack(stack === 'tv' ? 'movie' : 'tv')}
                  className="rounded-full border border-warm px-5 py-2.5 text-sm text-ink transition hover:border-amber"
                >
                  Try {stack === 'tv' ? 'Movies' : 'TV'} →
                </button>
              )}
            </div>
          ))}
      </div>

      <p className="mt-3 text-center text-xs text-muted/70">
        → like · ← dislike · ↑ watchlist · ↓ haven&apos;t seen — it learns as you go. Tap a card for
        details + the trailer.
      </p>

      <WishlistDrawer open={wishlistOpen} items={deck.wishlist} onClose={() => setWishlistOpen(false)} />
    </main>
  );
}
