'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';

import ResultsSummary from '@/components/ResultsSummary';
import SwipeDeck from '@/components/SwipeDeck';
import { ApiError, getRecommendations } from '@/lib/api';
import { useDeck } from '@/lib/deck';
import type { Recommendation, TasteProfile } from '@/lib/types';
import { decodeTitles, encodeTitles, titlesKey } from '@/lib/util';

type Status = 'loading' | 'ready' | 'error';

function ResultsInner() {
  const router = useRouter();
  const params = useSearchParams();
  const titles = useMemo(() => decodeTitles(params), [params]);
  const key = useMemo(() => titlesKey(titles), [titles]);

  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [profile, setProfile] = useState<TasteProfile | null>(null);
  const [status, setStatus] = useState<Status>('loading');
  const [errorMsg, setErrorMsg] = useState('');
  const [forceSummary, setForceSummary] = useState(false);
  const [shared, setShared] = useState(false);

  const deck = useDeck(recs, key);

  // No seeds → bounce back to the input screen.
  useEffect(() => {
    if (titles.length === 0) router.replace('/');
  }, [titles.length, router]);

  // Fetch a fresh deck whenever the seed titles change.
  useEffect(() => {
    if (titles.length === 0) return;
    let cancelled = false;
    setStatus('loading');
    setForceSummary(false);
    getRecommendations(titles, 20)
      .then((res) => {
        if (cancelled) return;
        setRecs(res.recommendations);
        setProfile(res.taste_profile);
        setStatus('ready');
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setErrorMsg(err instanceof ApiError ? err.message : 'Could not reach the recommender.');
        setStatus('error');
      });
    return () => {
      cancelled = true;
    };
  }, [key, titles]);

  const startOver = useCallback(() => router.push('/'), [router]);

  const getMore = useCallback(
    (likedTitles: string[]) => {
      if (likedTitles.length === 0) return;
      setForceSummary(false);
      router.push(`/results?${encodeTitles(likedTitles)}`);
    },
    [router],
  );

  function share() {
    if (!navigator.clipboard) return;
    navigator.clipboard.writeText(window.location.href).then(
      () => {
        setShared(true);
        window.setTimeout(() => setShared(false), 1500);
      },
      () => undefined,
    );
  }

  const showSummary = forceSummary || (deck.isDone && deck.total > 0);

  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col px-4 py-5">
      <header className="mb-4 flex items-center justify-between">
        <button type="button" onClick={startOver} className="text-sm text-muted transition hover:text-ink">
          ← Start over
        </button>
        <div className="flex items-center gap-2">
          {!showSummary && status === 'ready' && deck.total > 0 && (
            <button
              type="button"
              onClick={() => setForceSummary(true)}
              className="rounded-full border border-warm px-3 py-1.5 text-sm text-ink transition hover:border-amber"
            >
              See results
            </button>
          )}
          <button
            type="button"
            onClick={share}
            className="rounded-full border border-white/10 px-3 py-1.5 text-sm text-muted transition hover:text-ink"
          >
            {shared ? 'Copied ✓' : 'Share'}
          </button>
        </div>
      </header>

      <div className="flex flex-1 flex-col">
        {status === 'loading' && (
          <div className="flex flex-1 items-center justify-center">
            <p className="animate-pulse font-serif text-2xl text-muted">Building your deck…</p>
          </div>
        )}

        {status === 'error' && (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
            <p className="text-pass">{errorMsg}</p>
            <button
              type="button"
              onClick={startOver}
              className="rounded-full border border-warm px-5 py-2.5 text-ink transition hover:border-amber"
            >
              Try different titles
            </button>
          </div>
        )}

        {status === 'ready' &&
          (showSummary ? (
            <ResultsSummary
              liked={deck.liked}
              saved={deck.saved}
              tasteProfile={profile}
              onStartOver={startOver}
              onGetMore={getMore}
            />
          ) : (
            <SwipeDeck deck={deck} />
          ))}
      </div>
    </main>
  );
}

export default function ResultsPage() {
  return (
    <Suspense fallback={<div className="p-10 text-center text-muted">Loading…</div>}>
      <ResultsInner />
    </Suspense>
  );
}
