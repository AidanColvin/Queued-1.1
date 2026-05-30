'use client';

import { useState } from 'react';

import type { Recommendation, TasteProfile } from '@/lib/types';
import TasteRadar from './TasteRadar';

interface ResultsSummaryProps {
  liked: Recommendation[];
  saved: Recommendation[];
  tasteProfile: TasteProfile | null;
  onStartOver: () => void;
  onGetMore: (titles: string[]) => void;
}

function tmdbUrl(rec: Recommendation): string {
  if (rec.tmdb_id == null) return '#';
  return `https://www.themoviedb.org/${rec.type === 'tv' ? 'tv' : 'movie'}/${rec.tmdb_id}`;
}

function PosterGrid({ items }: { items: Recommendation[] }) {
  if (items.length === 0) {
    return <p className="py-10 text-center text-muted">Nothing here yet.</p>;
  }
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      {items.map((rec) => (
        <a
          key={rec.tmdb_id ?? rec.title}
          href={tmdbUrl(rec)}
          target="_blank"
          rel="noreferrer"
          className="group overflow-hidden rounded-lg border border-warm bg-surface transition hover:border-amber"
        >
          <div className="aspect-[2/3] w-full bg-gradient-to-br from-surface-2 to-black">
            {rec.poster_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={rec.poster_url} alt={rec.title} loading="lazy" className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full items-center justify-center p-3 text-center font-serif text-sm text-white/30">
                {rec.title}
              </div>
            )}
          </div>
          <div className="p-2">
            <p className="truncate text-sm text-ink">{rec.title}</p>
            <p className="text-xs text-muted">{rec.year ?? ''}</p>
          </div>
        </a>
      ))}
    </div>
  );
}

export default function ResultsSummary({
  liked,
  saved,
  tasteProfile,
  onStartOver,
  onGetMore,
}: ResultsSummaryProps) {
  const [tab, setTab] = useState<'liked' | 'saved'>('liked');
  const [copied, setCopied] = useState(false);

  function copyWatchlist() {
    const text = saved.map((r) => `${r.title}${r.year ? ` (${r.year})` : ''}`).join('\n');
    if (!navigator.clipboard) return;
    navigator.clipboard.writeText(text).then(
      () => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
      },
      () => undefined,
    );
  }

  return (
    <div className="mx-auto w-full max-w-3xl animate-fade-in">
      <h2 className="text-center font-serif text-4xl text-ink">Your picks</h2>

      {/* Taste snapshot */}
      <div className="mt-6 grid gap-6 rounded-2xl border border-warm bg-surface/60 p-5 sm:grid-cols-2">
        <TasteRadar liked={liked} />
        <div className="flex flex-col justify-center gap-3">
          <div>
            <p className="text-xs uppercase tracking-wide text-muted">Top genres</p>
            <p className="text-lg text-ink">{tasteProfile?.top_genres.join(' · ') || '—'}</p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-muted">Mood</p>
            <div className="mt-1 flex flex-wrap gap-1.5">
              {(tasteProfile?.mood_tags ?? []).map((m) => (
                <span key={m} className="rounded-full bg-white/10 px-2 py-0.5 text-xs text-ink/80">
                  {m}
                </span>
              ))}
            </div>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-muted">Era</p>
            <p className="text-lg text-ink">{tasteProfile?.era_bias ?? '—'}</p>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="mt-6 flex items-center justify-center gap-2">
        {(['liked', 'saved'] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`rounded-full px-4 py-1.5 text-sm capitalize transition ${
              tab === t ? 'bg-amber text-charcoal' : 'border border-warm text-muted hover:text-ink'
            }`}
          >
            {t} ({t === 'liked' ? liked.length : saved.length})
          </button>
        ))}
      </div>

      <div className="mt-4">
        <PosterGrid items={tab === 'liked' ? liked : saved} />
      </div>

      {/* Actions */}
      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        <button
          type="button"
          onClick={() => onGetMore(liked.map((r) => r.title))}
          disabled={liked.length === 0}
          className="rounded-full bg-amber px-6 py-3 font-medium text-charcoal transition hover:brightness-110 disabled:opacity-40"
        >
          Get more like these →
        </button>
        {tab === 'saved' && saved.length > 0 && (
          <button
            type="button"
            onClick={copyWatchlist}
            className="rounded-full border border-warm px-5 py-3 text-ink transition hover:border-amber"
          >
            {copied ? 'Copied ✓' : 'Copy watchlist'}
          </button>
        )}
        <button
          type="button"
          onClick={onStartOver}
          className="rounded-full border border-white/10 px-5 py-3 text-muted transition hover:text-ink"
        >
          Start over
        </button>
      </div>
    </div>
  );
}
