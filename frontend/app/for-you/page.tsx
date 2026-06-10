'use client';

import { useCallback, useEffect, useState } from 'react';

import { getPersonal } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { loadStoredPositiveTitles } from '@/lib/deck';
import { resolvePoster } from '@/lib/posters';
import { PROVIDER_BY_ID, loadProviderFilter, loadSelectedProviders } from '@/lib/providers';
import type { PersonalResponse, Recommendation } from '@/lib/types';
import TrailerModal from '@/components/TrailerModal';

/** The "For You" page: ranked shelves built from everything known about the
 *  viewer — saved likes, swipes, imported Letterboxd ratings. Guests get
 *  session-seeded shelves plus a sign-in nudge. */
export default function ForYouPage() {
  const { user, loading } = useAuth();
  const [data, setData] = useState<PersonalResponse | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [trailerRec, setTrailerRec] = useState<Recommendation | null>(null);

  const fetchShelves = useCallback(() => {
    setStatus('loading');
    const prefs = { filter: loadProviderFilter(), providers: loadSelectedProviders() };
    // Guests bring their local session likes; the cookie identifies users.
    const seeds = user ? [] : loadStoredPositiveTitles();
    getPersonal(seeds, prefs)
      .then((res) => {
        setData(res);
        setStatus('ready');
      })
      .catch(() => setStatus('error'));
  }, [user]);

  // Wait for the auth check so a signed-in user's first fetch uses the cookie.
  useEffect(() => {
    if (!loading) fetchShelves();
  }, [loading, fetchShelves]);

  return (
    <main className="app-shell mx-auto flex w-full max-w-md flex-col">
      <header className="mb-4 flex items-center justify-between gap-2">
        <a href="/" className="text-sm font-medium text-muted transition hover:text-ink">
          ← Deck
        </a>
        <span className="text-[17px] font-semibold tracking-tight text-ink">For You</span>
        <span className="w-12" aria-hidden />
      </header>

      {status === 'loading' && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4">
          <div className="h-7 w-7 animate-spin rounded-full border-[3px] border-surface-2 border-t-accent" />
          <p className="text-[15px] text-muted">Reading your taste…</p>
        </div>
      )}

      {status === 'error' && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
          <p className="text-[15px] text-muted">Couldn&apos;t load your recommendations.</p>
          <button
            type="button"
            onClick={fetchShelves}
            className="rounded-full bg-accent px-5 py-2.5 text-sm font-medium text-white transition hover:brightness-110 active:scale-95"
          >
            Try again
          </button>
        </div>
      )}

      {status === 'ready' && data && (
        <div className="space-y-6 pb-6">
          {!data.signed_in && (
            <div className="rounded-2xl bg-surface p-4 ring-1 ring-black/[0.06]">
              <p className="text-sm text-ink">
                These picks come from this session only.{' '}
                <a href="/" className="font-medium text-accent hover:underline">
                  Sign in
                </a>{' '}
                and NextWatch will use everything you&apos;ve ever liked — including your Letterboxd ratings.
              </p>
            </div>
          )}

          {data.seeded_by.length > 0 && (
            <p className="text-xs text-muted">
              Based on {data.seeded_by.slice(0, 4).join(', ')}
              {data.seeded_by.length > 4 ? ` and ${data.seeded_by.length - 4} more` : ''}.
            </p>
          )}

          {data.sections.map((section) => (
            <section key={section.key}>
              <h2 className="mb-2 text-[15px] font-semibold tracking-tight text-ink">{section.title}</h2>
              <div className="-mx-1 flex snap-x gap-3 overflow-x-auto px-1 pb-2">
                {section.items.map((rec) => (
                  <ShelfCard key={`${section.key}-${rec.id}`} rec={rec} onOpen={() => setTrailerRec(rec)} />
                ))}
              </div>
            </section>
          ))}

          {data.sections.length === 0 && (
            <p className="text-center text-sm text-muted">
              Nothing yet — swipe a few titles on the deck and come back.
            </p>
          )}

          <p className="text-center text-[10px] text-faint">Streaming availability data by JustWatch via TMDB.</p>
        </div>
      )}

      <TrailerModal rec={trailerRec} onClose={() => setTrailerRec(null)} />
    </main>
  );
}

/** One poster tile in a shelf — tap to play the trailer. */
function ShelfCard({ rec, onOpen }: { rec: Recommendation; onOpen: () => void }) {
  const [poster, setPoster] = useState<string | null>(rec.poster_url);
  useEffect(() => {
    let cancelled = false;
    if (!rec.poster_url) {
      resolvePoster(rec).then((url) => {
        if (!cancelled) setPoster(url);
      });
    }
    return () => {
      cancelled = true;
    };
  }, [rec]);

  return (
    <button
      type="button"
      onClick={onOpen}
      className="w-32 shrink-0 snap-start text-left transition active:scale-95"
      aria-label={`${rec.title} — play trailer`}
    >
      <div className="relative h-48 w-32 overflow-hidden rounded-2xl bg-surface-2 shadow-soft ring-1 ring-black/5">
        {poster ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={poster} alt={`${rec.title} poster`} loading="lazy" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full w-full items-center justify-center p-2 text-center text-xs font-medium text-muted">
            {rec.title}
          </div>
        )}
        {(rec.providers ?? []).slice(0, 2).map((id, i) => {
          const p = PROVIDER_BY_ID.get(id);
          return p ? (
            <span
              key={id}
              className="absolute rounded-full px-1.5 py-0.5 text-[9px] font-semibold text-white"
              style={{ backgroundColor: p.color, top: 6, left: 6 + i * 44 }}
            >
              {p.short}
            </span>
          ) : null;
        })}
      </div>
      <p className="mt-1.5 truncate text-xs font-medium text-ink">{rec.title}</p>
      <p className="line-clamp-2 text-[10px] leading-snug text-muted">{rec.why}</p>
    </button>
  );
}
