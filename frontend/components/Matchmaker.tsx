'use client';

import { useEffect, useState } from 'react';

import { ApiError, getTasteMatch, type TasteMatch } from '@/lib/api';
import { getSessionId } from '@/lib/util';

/**
 * Compare two taste profiles and show a 0–100% match rate. Light, on-brand card
 * (matches the rest of the app — the previous dark glass build was invisible on
 * the white For You page). "Your session id" is prefilled with this visitor's
 * own id so the feature is usable without hunting for it.
 */
export default function Matchmaker() {
  const [userA, setUserA] = useState('');
  const [userB, setUserB] = useState('');
  const [match, setMatch] = useState<TasteMatch | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // Prefill the caller's own session id (client-only, avoids SSR mismatch).
  useEffect(() => {
    setUserA((prev) => prev || getSessionId());
  }, []);

  const checkMatch = async () => {
    if (!userA.trim() || !userB.trim() || loading) return;
    setLoading(true);
    setError(null);
    setMatch(null);
    try {
      setMatch(await getTasteMatch(userA.trim(), userB.trim()));
    } catch (e) {
      setError(
        e instanceof ApiError && e.status === 404
          ? 'No taste profile yet — both people need to swipe a few cards first.'
          : 'Could not compare profiles. Try again.',
      );
    } finally {
      setLoading(false);
    }
  };

  const inputCls =
    'w-full rounded-xl bg-surface-2 px-4 py-2.5 text-sm text-ink ring-1 ring-black/[0.06] transition placeholder:text-faint focus:outline-none focus:ring-2 focus:ring-accent';

  return (
    <div className="my-8 w-full rounded-3xl bg-surface p-6 shadow-card ring-1 ring-black/5">
      <h3 className="text-lg font-semibold tracking-tight text-ink">Taste Matchmaker</h3>
      <p className="mb-5 mt-1 text-sm text-muted">Compare your taste with a friend by session id.</p>

      <div className="mb-4 flex flex-col gap-3 md:flex-row">
        <input
          type="text"
          placeholder="Your session id"
          className={inputCls}
          value={userA}
          onChange={(e) => setUserA(e.target.value)}
        />
        <input
          type="text"
          placeholder="Friend's session id"
          className={inputCls}
          value={userB}
          onChange={(e) => setUserB(e.target.value)}
        />
      </div>

      <button
        type="button"
        onClick={checkMatch}
        disabled={loading || !userB.trim()}
        className="w-full rounded-xl bg-ink py-2.5 text-sm font-medium text-white transition hover:brightness-125 active:scale-[0.99] disabled:opacity-40"
      >
        {loading ? 'Comparing…' : 'Calculate compatibility'}
      </button>

      {match && (
        <div className="mt-5 rounded-2xl bg-surface-2 p-4 text-center ring-1 ring-black/[0.06]">
          <p className="text-sm text-muted">Match rate</p>
          <p className="mt-0.5 text-5xl font-semibold tracking-tight text-accent">
            {match.match_percentage}%
          </p>
        </div>
      )}

      {error && (
        <p className="mt-4 rounded-xl bg-pass/10 px-3 py-2.5 text-center text-sm text-pass">{error}</p>
      )}
    </div>
  );
}
