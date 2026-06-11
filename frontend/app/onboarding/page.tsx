'use client';

import { useEffect, useState } from 'react';

import { getMyProviders, setMyProviders } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { PROVIDERS, loadSelectedProviders, saveSelectedProviders } from '@/lib/providers';

/** The one-time "which streaming services do you have?" screen.
 *
 *  New accounts land here right after their first sign-up; it is also reachable
 *  any time from the account menu to edit the selection. Saving (or skipping)
 *  marks onboarding complete server-side so the screen never auto-appears
 *  again. Guests can use it too — their selection lives in localStorage and is
 *  merged into the account when they sign up.
 */
export default function OnboardingPage() {
  const { user, loading } = useAuth();
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Prefill: local selection immediately, then the account's saved one.
  useEffect(() => {
    setSelected(new Set(loadSelectedProviders()));
  }, []);
  useEffect(() => {
    if (!user) return;
    getMyProviders()
      .then((mine) => {
        if (mine.providers.length) setSelected(new Set(mine.providers));
      })
      .catch(() => {
        /* fall back to the local selection */
      });
  }, [user]);

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  // Save commits the highlighted selection; Skip keeps whatever was already
  // saved and just marks onboarding done so the screen stops auto-appearing.
  const finish = async (mode: 'save' | 'skip') => {
    setBusy(true);
    setError(null);
    const ids = mode === 'save' ? [...selected] : loadSelectedProviders();
    if (mode === 'save') saveSelectedProviders(ids);
    try {
      if (user) await setMyProviders(ids, true);
      window.location.href = '/';
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save. Try again.');
      setBusy(false);
    }
  };

  return (
    <main className="app-shell mx-auto flex w-full max-w-md flex-col">
      <header className="mb-6 mt-2 text-center">
        <h1 className="text-2xl font-bold tracking-tight text-ink">Where do you watch?</h1>
        <p className="mt-1.5 text-sm text-muted">
          Pick your streaming services and Queued can stick to titles you can actually press play on. You can
          change this anytime from the account menu.
        </p>
      </header>

      <div className="grid grid-cols-2 gap-3">
        {PROVIDERS.map((p) => {
          const active = selected.has(p.id);
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => toggle(p.id)}
              aria-pressed={active}
              className={`flex h-20 flex-col items-center justify-center gap-1 rounded-2xl text-base font-semibold transition active:scale-95 ${
                active ? 'text-white shadow-card' : 'bg-surface text-ink ring-1 ring-black/[0.08] hover:ring-black/20'
              }`}
              style={active ? { backgroundColor: p.color } : undefined}
            >
              {p.name}
              <span className={`text-[11px] font-normal ${active ? 'text-white/80' : 'text-muted'}`}>
                {active ? 'Added ✓' : 'Tap to add'}
              </span>
            </button>
          );
        })}
      </div>

      {error && <p className="mt-4 text-center text-sm text-pass">{error}</p>}

      <div className="mt-6 space-y-2">
        <button
          type="button"
          disabled={busy || loading}
          onClick={() => void finish('save')}
          className="w-full rounded-xl bg-accent px-4 py-3 text-sm font-semibold text-white transition hover:brightness-110 active:scale-[0.98] disabled:opacity-50"
        >
          {busy ? 'Saving…' : selected.size ? `Save ${selected.size} service${selected.size > 1 ? 's' : ''}` : 'Save'}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={() => void finish('skip')}
          className="w-full rounded-xl px-4 py-2.5 text-sm font-medium text-muted transition hover:text-ink"
        >
          Skip for now
        </button>
      </div>

      <p className="mt-6 text-center text-[11px] text-faint">Streaming availability data by JustWatch via TMDB.</p>
    </main>
  );
}
