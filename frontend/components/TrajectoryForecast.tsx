'use client';

import { useEffect, useState } from 'react';

import { getSessionId } from '@/lib/util';

interface ForecastTitle {
  id: number;
  title: string;
  year?: number | null;
  score: number;
}

interface Forecast {
  loves: ForecastTitle[];
  hates: ForecastTitle[];
  personalized: boolean;
  loading: boolean;
}

/**
 * The Crystal Ball: what the engine predicts this viewer will love and hate
 * next, scored by the real production model against the caller's own taste
 * vector (the one their swipes train). Light, on-brand card — the original
 * dark-glass build was unreadable on the white For You page.
 */
export default function TrajectoryForecast() {
  const [forecast, setForecast] = useState<Forecast>({
    loves: [],
    hates: [],
    personalized: false,
    loading: true,
  });

  useEffect(() => {
    const apiUrl = (process.env.NEXT_PUBLIC_API_URL ?? '/api').replace(/\/$/, '');
    fetch(`${apiUrl}/predict/crystal-ball?session_id=${encodeURIComponent(getSessionId())}`, {
      credentials: 'include',
    })
      .then((r) => r.json())
      .then((data) =>
        setForecast({
          loves: data.loves ?? [],
          hates: data.hates ?? [],
          personalized: Boolean(data.personalized),
          loading: false,
        }),
      )
      .catch(() => setForecast((f) => ({ ...f, loading: false })));
  }, []);

  if (forecast.loading) {
    return <div className="h-28 animate-pulse rounded-2xl bg-surface-2" aria-hidden />;
  }
  if (!forecast.loves.length) return null;

  return (
    <section className="rounded-2xl bg-surface p-4 ring-1 ring-black/[0.06]">
      <h2 className="text-[15px] font-semibold tracking-tight text-ink">Crystal ball 🔮</h2>
      <p className="mt-0.5 text-xs text-muted">
        {forecast.personalized
          ? 'Predicted from your swipes by the taste model.'
          : 'Crowd favorites for now — swipe a few titles and this becomes your forecast.'}
      </p>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <div>
          <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-emerald-700">
            Predicted to love
          </h3>
          {forecast.loves.map((m) => (
            <div key={m.id} className="mb-1 flex items-center justify-between gap-2">
              <span className="truncate text-sm text-ink">
                {m.title}
                {m.year ? <span className="text-muted"> ({m.year})</span> : null}
              </span>
              <span className="shrink-0 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
                {Math.round(Math.min(0.99, Math.max(0, (m.score + 1) / 2.6)) * 100)}%
              </span>
            </div>
          ))}
        </div>

        {forecast.hates.length > 0 && (
          <div>
            <h3 className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-rose-700">
              Predicted to skip
            </h3>
            {forecast.hates.map((m) => (
              <div key={m.id} className="mb-1 flex items-center justify-between gap-2">
                <span className="truncate text-sm text-ink">
                  {m.title}
                  {m.year ? <span className="text-muted"> ({m.year})</span> : null}
                </span>
                <span className="shrink-0 rounded-full bg-rose-50 px-2 py-0.5 text-[11px] font-medium text-rose-700">
                  not your taste
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
