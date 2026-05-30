'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { getPopular, getRecommendations } from '@/lib/api';
import { useDeck } from '@/lib/deck';
import type { Recommendation } from '@/lib/types';
import { youtubeTrailerUrl } from '@/lib/util';
import SwipeDeck from './SwipeDeck';
import WishlistDrawer from './WishlistDrawer';

interface DeckExperienceProps {
  /** Optional seed titles (shared links). Empty → popular cold-start deck. */
  seedTitles?: string[];
}

const REFILL_AT = 5; // fetch more when this few cards remain
const REFILL_COUNT = 15;

export default function DeckExperience({ seedTitles = [] }: DeckExperienceProps) {
  const deck = useDeck();
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [wishlistOpen, setWishlistOpen] = useState(false);
  const fetchingRef = useRef(false);
  const startedRef = useRef(false);

  // Pull the next batch of cards, adapting to what the user has liked so far.
  const fetchMore = useCallback(
    async (initial: boolean) => {
      if (fetchingRef.current) return;
      fetchingRef.current = true;
      try {
        const seeds = deck.positiveTitles.length ? deck.positiveTitles : seedTitles;
        const res = seeds.length
          ? await getRecommendations(seeds, REFILL_COUNT, deck.knownIds)
          : await getPopular(initial ? 20 : REFILL_COUNT, deck.knownIds);
        deck.append(res.recommendations);
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
    void fetchMore(true);
  }, [fetchMore]);

  // Endless refill: keep the queue topped up as the user swipes.
  useEffect(() => {
    if (status === 'ready' && deck.upcomingCount <= REFILL_AT) {
      void fetchMore(false);
    }
  }, [status, deck.upcomingCount, fetchMore]);

  const openCard = useCallback((rec: Recommendation) => {
    window.open(youtubeTrailerUrl(rec.title, rec.year), '_blank', 'noopener,noreferrer');
  }, []);

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col px-4 py-5">
      <header className="mb-3 flex items-center justify-between">
        <span className="text-sm font-semibold uppercase tracking-[0.25em] text-amber/80">NextWatch</span>
        <button
          type="button"
          onClick={() => setWishlistOpen(true)}
          className="rounded-full border border-warm px-4 py-1.5 text-sm text-ink transition hover:border-amber"
        >
          Watchlist{deck.wishlist.length ? ` (${deck.wishlist.length})` : ''}
        </button>
      </header>

      <div className="flex flex-1 flex-col">
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
                void fetchMore(true);
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
            <div className="flex flex-1 items-center justify-center">
              <p className="animate-pulse font-serif text-2xl text-muted">Lining up more picks…</p>
            </div>
          ))}
      </div>

      <p className="mt-3 text-center text-xs text-muted/70">
        → like · ← pass · ↑ watchlist · ↓ skip — it learns as you go. Tap a card for the trailer.
      </p>

      <WishlistDrawer open={wishlistOpen} items={deck.wishlist} onClose={() => setWishlistOpen(false)} />
    </main>
  );
}
