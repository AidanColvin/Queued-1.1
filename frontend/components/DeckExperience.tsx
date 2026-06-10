'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import {
  getHistory,
  getMyProviders,
  getPopular,
  getRecommendations,
  getTv,
  mergeGuestData,
  saveTitle,
} from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { useDeck } from '@/lib/deck';
import { resolvePoster } from '@/lib/posters';
import {
  FILTER_LABELS,
  NEXT_FILTER,
  loadProviderFilter,
  loadSelectedProviders,
  saveProviderFilter,
  saveSelectedProviders,
} from '@/lib/providers';
import type { ProviderFilter, ProviderPrefs, Recommendation, SwipeAction } from '@/lib/types';
import AccountMenu from './AccountMenu';
import AuthModal from './AuthModal';
import LetterboxdModal from './LetterboxdModal';
import SplashScreen from './SplashScreen';
import SwipeDeck from './SwipeDeck';
import TrailerModal from './TrailerModal';
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
  const { user } = useAuth();
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [wishlistOpen, setWishlistOpen] = useState(false);
  const [authOpen, setAuthOpen] = useState(false);
  const [letterboxdOpen, setLetterboxdOpen] = useState(false);
  const [trailerRec, setTrailerRec] = useState<Recommendation | null>(null);
  const [stack, setStack] = useState<Stack>('movie');
  // Streaming-service filter: three-state toggle + the viewer's services.
  const [provFilter, setProvFilter] = useState<ProviderFilter>('all');
  const [myProviders, setMyProviders] = useState<number[]>([]);
  const fetchingRef = useRef(false);
  const startedRef = useRef(false);
  const exhaustedRef = useRef(false);
  const prevUserRef = useRef<typeof user>(null);
  const onboardingSentRef = useRef(false);

  // Restore the locally saved filter + services once on mount.
  useEffect(() => {
    setProvFilter(loadProviderFilter());
    setMyProviders(loadSelectedProviders());
  }, []);

  const providerPrefs: ProviderPrefs = { filter: provFilter, providers: myProviders };
  const prefsRef = useRef(providerPrefs);
  prefsRef.current = providerPrefs;

  // Users should only ever see cards with a real poster. Keep a rec only if it
  // already has a poster (movies) or one can be resolved keylessly (TV → TVmaze);
  // anything still without artwork is dropped so no placeholder tile is shown.
  const keepPostered = useCallback(async (recs: Recommendation[]): Promise<Recommendation[]> => {
    const resolved = await Promise.all(
      recs.map(async (r) => {
        // Movies must already carry a (real) poster. TV always resolves so we can
        // prefer TVmaze's portrait art over the catalog's logo/low-res image.
        if (r.type !== 'tv') return r.poster_url ? r : null;
        const url = await resolvePoster(r);
        return url ? { ...r, poster_url: url } : null;
      }),
    );
    return resolved.filter((r): r is Recommendation => r !== null);
  }, []);

  // Pull the next batch for the active stack. Movies are ML-personalized (seeded
  // by what you've liked); TV is a separate popularity-ranked catalog. `initial`
  // requests start from a clean slate so switching stacks never carries excludes.
  const fetchMore = useCallback(
    async (initial: boolean, forStack: Stack) => {
      if (fetchingRef.current) return;
      fetchingRef.current = true;
      // The backend runs as a serverless function, so the very first request
      // after it's been idle pays a cold start — the ML model loads AND the free
      // Postgres (Neon) resumes from suspend — which together can take tens of
      // seconds. Retry the initial load with a generous backoff so the deck always
      // appears and the user is never stranded on "Couldn't reach" with nothing to
      // swipe. Refills only try once (a card is already on screen).
      const attempts = initial ? 8 : 1;
      try {
        for (let attempt = 1; attempt <= attempts; attempt += 1) {
          try {
            // Always exclude everything seen — on the initial load this is the
            // persisted seen set (so reloads never repeat cards), on refills it's
            // that plus the current queue.
            const exclude = deck.knownIds;
            const count = initial ? 20 : REFILL_COUNT;
            const prefs = prefsRef.current;
            let res;
            if (forStack === 'tv') {
              res = await getTv(count, exclude, prefs);
            } else {
              const seeds = deck.positiveTitles.length ? deck.positiveTitles : seedTitles;
              // Adaptive when we have movie seeds; fall back to popular if /recommend
              // can't resolve them (or fails), so the deck never dead-ends.
              res = seeds.length
                ? await getRecommendations(seeds, REFILL_COUNT, exclude, prefs).catch(() =>
                    getPopular(count, exclude, prefs),
                  )
                : await getPopular(count, exclude, prefs);
            }
            const fetched = res.recommendations;
            // Drop anything we can't show a poster for before it enters the deck.
            const postered = await keepPostered(fetched);
            // Queue the postered cards, but mark the *whole* fetched batch seen so
            // dropped (poster-less) titles are excluded from future fetches. When
            // a batch yields no postered cards, the refill effect re-fires and
            // pulls the next batch automatically (the excludes have grown).
            deck.append(postered, fetched);
            if (!initial && fetched.length === 0) exhaustedRef.current = true; // catalog drained
            setStatus('ready');
            return;
          } catch (err) {
            if (attempt >= attempts) {
              if (initial) setStatus('error');
            } else {
              // Backoff: 2.5s, 5s, 7.5s, then capped at 9s ≈ 50s total patience —
              // enough to ride out a cold start plus a Neon resume.
              await new Promise((r) => setTimeout(r, Math.min(2500 * attempt, 9000)));
            }
          }
        }
      } finally {
        fetchingRef.current = false;
      }
    },
    [deck, seedTitles, keepPostered],
  );

  // Initial load (once) — wait until localStorage has been restored so the
  // first fetch already excludes everything seen in previous sessions.
  useEffect(() => {
    if (startedRef.current || !deck.hydrated) return;
    startedRef.current = true;
    void fetchMore(true, 'movie');
  }, [fetchMore, deck.hydrated]);

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

  // The deck contents depend on the streaming filter, so changing it starts a
  // fresh (still exclude-aware) deck.
  const applyFilter = useCallback(
    (next: ProviderFilter) => {
      setProvFilter(next);
      saveProviderFilter(next);
      exhaustedRef.current = false;
      deck.reset();
      setStatus('loading');
      // prefsRef updates on the next render; pass the new filter explicitly.
      prefsRef.current = { filter: next, providers: myProviders };
      void fetchMore(true, stack);
    },
    [myProviders, deck, fetchMore, stack],
  );

  // Cycle All → Only → Prefer → All.
  const cycleFilter = useCallback(() => applyFilter(NEXT_FILTER[provFilter]), [applyFilter, provFilter]);

  // First sign-in on this device: pull the account's saved services; and if the
  // account has never been through onboarding, send it there once.
  useEffect(() => {
    if (!user) return;
    getMyProviders()
      .then((mine) => {
        if (mine.providers.length) {
          setMyProviders(mine.providers);
          saveSelectedProviders(mine.providers);
        }
      })
      .catch(() => {
        /* keep the local selection */
      });
    if (!user.onboarding_completed && !onboardingSentRef.current) {
      onboardingSentRef.current = true;
      window.location.href = '/onboarding/';
    }
  }, [user]);

  // Keep the deck in sync with the account across sign-in / sign-out.
  useEffect(() => {
    if (!deck.hydrated) return;
    const was = prevUserRef.current;
    prevUserRef.current = user;
    if (!was && user) {
      // Signed in: merge any local guest state into the account, then adopt the
      // authoritative server state. Idempotent — a reload while already logged
      // in just re-merges the mirrored local copy (a no-op) and reloads history.
      mergeGuestData({ liked: deck.liked, wishlist: deck.wishlist, seen: deck.knownIds })
        .then((hist) => deck.loadServerState(hist))
        .catch(() => {
          /* offline / server hiccup — keep local state, try again next load */
        });
      // Strip the ?login=success the Google redirect lands on.
      if (typeof window !== 'undefined' && window.location.search.includes('login=')) {
        window.history.replaceState({}, '', window.location.pathname);
      }
    } else if (was && !user) {
      // Signed out: drop personal state and start a fresh anonymous deck.
      deck.clearAll();
      exhaustedRef.current = false;
      setStatus('loading');
      void fetchMore(true, stack);
    }
  }, [user, deck, fetchMore, stack]);

  // While signed in, persist a liked/saved card to the account (fire-and-forget)
  // so the watchlist follows the user across devices.
  const persistSave = useCallback(
    (rec: Recommendation, action: SwipeAction) => {
      if (!user) return;
      if (action === 'saved') saveTitle(rec, 'wishlist').catch(() => {});
      else if (action === 'liked' || action === 'superliked') saveTitle(rec, 'liked').catch(() => {});
    },
    [user],
  );

  // Open the trailer in an in-page player instead of navigating to YouTube.
  const openCard = useCallback((rec: Recommendation) => {
    setTrailerRec(rec);
  }, []);

  // Apple-style segmented control: a single pill track with the active segment
  // lifted onto a white, softly-shadowed chip.
  const segBtn = (active: boolean) =>
    `rounded-full px-4 py-1.5 text-sm font-medium transition ${
      active ? 'bg-white text-ink shadow-soft ring-1 ring-black/[0.04]' : 'text-muted hover:text-ink'
    }`;

  return (
    <main className="app-shell mx-auto flex w-full max-w-md flex-col">
      <SplashScreen />
      <header className="mb-4 flex items-center justify-between gap-2">
        <span className="text-[17px] font-semibold tracking-tight text-ink">NextWatch</span>

        <div className="flex items-center gap-2">
          <div className="flex items-center rounded-full bg-black/[0.04] p-0.5">
            <button type="button" onClick={() => switchStack('movie')} className={segBtn(stack === 'movie')}>
              Movies
            </button>
            <button type="button" onClick={() => switchStack('tv')} className={segBtn(stack === 'tv')}>
              TV
            </button>
          </div>
          <button
            type="button"
            onClick={() => setWishlistOpen(true)}
            aria-label="Open watchlist"
            className="flex items-center gap-1.5 rounded-full bg-white px-3.5 py-2 text-sm font-medium text-ink ring-1 ring-black/[0.08] transition hover:ring-black/20 active:scale-95"
          >
            <span>Watchlist</span>
            {deck.wishlist.length ? (
              <span className="tabular-nums text-muted">{deck.wishlist.length}</span>
            ) : null}
          </button>

          {user ? (
            <AccountMenu user={user} onConnectLetterboxd={() => setLetterboxdOpen(true)} />
          ) : (
            <button
              type="button"
              onClick={() => setAuthOpen(true)}
              className="rounded-full bg-ink px-3.5 py-2 text-sm font-medium text-white transition hover:brightness-125 active:scale-95"
            >
              Sign in
            </button>
          )}
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col">
        {status === 'loading' && (
          <div className="flex flex-1 flex-col items-center justify-center gap-4">
            <div className="h-7 w-7 animate-spin rounded-full border-[3px] border-surface-2 border-t-accent" />
            <p className="text-[15px] text-muted">Finding something to watch…</p>
          </div>
        )}

        {status === 'error' && (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
            <p className="text-[15px] text-muted">Couldn&apos;t reach the recommender.</p>
            <button
              type="button"
              onClick={() => {
                setStatus('loading');
                void fetchMore(true, stack);
              }}
              className="rounded-full bg-accent px-5 py-2.5 text-sm font-medium text-white transition hover:brightness-110 active:scale-95"
            >
              Try again
            </button>
          </div>
        )}

        {status === 'ready' &&
          (deck.currentCard ? (
            <SwipeDeck deck={deck} onOpenCard={openCard} onPersistSave={persistSave} providerPrefs={providerPrefs} />
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
              <p className="text-[17px] font-medium text-ink">
                {exhaustedRef.current
                  ? provFilter === 'only'
                    ? "That's everything on your services."
                    : `That's every popular ${stack === 'tv' ? 'show' : 'title'} — nice swiping.`
                  : 'Lining up more picks…'}
              </p>
              {exhaustedRef.current &&
                (provFilter === 'only' ? (
                  <button
                    type="button"
                    onClick={() => applyFilter('all')}
                    className="rounded-full bg-accent px-5 py-2.5 text-sm font-medium text-white transition hover:brightness-110 active:scale-95"
                  >
                    Show all titles →
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => switchStack(stack === 'tv' ? 'movie' : 'tv')}
                    className="rounded-full bg-accent px-5 py-2.5 text-sm font-medium text-white transition hover:brightness-110 active:scale-95"
                  >
                    Try {stack === 'tv' ? 'Movies' : 'TV'} →
                  </button>
                ))}
            </div>
          ))}
      </div>

      <div className="mt-4 flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={cycleFilter}
          aria-label={`Streaming filter: ${FILTER_LABELS[provFilter]}`}
          title="Cycle: all titles → only my services → boost my services"
          className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-xs font-medium transition active:scale-95 ${
            provFilter === 'all'
              ? 'bg-white text-muted ring-1 ring-black/[0.08] hover:text-ink'
              : 'bg-ink text-white'
          }`}
        >
          <span aria-hidden>{provFilter === 'all' ? '◯' : provFilter === 'only' ? '●' : '◐'}</span>
          {FILTER_LABELS[provFilter]}
        </button>
        {provFilter !== 'all' && myProviders.length === 0 && (
          <a href="/onboarding/" className="text-xs font-medium text-accent hover:underline">
            Pick your services →
          </a>
        )}
        <a
          href="/for-you/"
          className="flex items-center gap-1.5 rounded-full bg-white px-3.5 py-1.5 text-xs font-medium text-ink ring-1 ring-black/[0.08] transition hover:ring-black/20 active:scale-95"
        >
          <span aria-hidden>✦</span> Recommendations
        </a>
      </div>

      <p className="mt-3 text-center text-xs text-faint">
        Swipe or tap the arrows — it learns as you go. Tap a card to watch the trailer.
      </p>
      <p className="mt-1 text-center text-[10px] text-faint">Streaming availability data by JustWatch via TMDB.</p>

      <WishlistDrawer open={wishlistOpen} items={deck.wishlist} onClose={() => setWishlistOpen(false)} />
      <TrailerModal rec={trailerRec} onClose={() => setTrailerRec(null)} />
      <AuthModal open={authOpen} onClose={() => setAuthOpen(false)} />
      <LetterboxdModal
        open={letterboxdOpen}
        onClose={() => setLetterboxdOpen(false)}
        onImported={() => {
          // Adopt the imported likes/seen so the live deck stops serving them.
          getHistory()
            .then((hist) => deck.loadServerState(hist))
            .catch(() => {});
        }}
      />
    </main>
  );
}
