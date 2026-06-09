'use client';

import { useEffect, useState } from 'react';

import { getTrailer } from '@/lib/api';
import type { Recommendation } from '@/lib/types';
import { youtubeTrailerUrl } from '@/lib/util';

interface TrailerModalProps {
  /** The card whose trailer to play, or null when the modal is closed. */
  rec: Recommendation | null;
  onClose: () => void;
}

type Phase =
  | { state: 'loading' }
  | { state: 'playing'; key: string }
  | { state: 'unavailable' };

/**
 * Plays a title's trailer in an embedded YouTube player *inside the app* — the
 * user never leaves NextWatch. Resolves the video id from the backend (`/trailer`,
 * TMDB-backed); if none is available it degrades to an explicit "open on YouTube"
 * link rather than auto-navigating away.
 */
export default function TrailerModal({ rec, onClose }: TrailerModalProps) {
  const [phase, setPhase] = useState<Phase>({ state: 'loading' });

  // Resolve the trailer whenever a new card opens the modal.
  useEffect(() => {
    if (!rec) return;
    let cancelled = false;
    setPhase({ state: 'loading' });

    // Prefer the keyless trailer id baked into the catalog — plays in-page with
    // no API call at all. Only fall back to the TMDB-backed lookup when absent.
    if (rec.trailer_key) {
      setPhase({ state: 'playing', key: rec.trailer_key });
      return;
    }
    if (rec.tmdb_id == null) {
      setPhase({ state: 'unavailable' });
      return;
    }
    getTrailer(rec.tmdb_id, rec.type)
      .then((res) => {
        if (cancelled) return;
        setPhase(res.youtube_key ? { state: 'playing', key: res.youtube_key } : { state: 'unavailable' });
      })
      .catch(() => {
        if (!cancelled) setPhase({ state: 'unavailable' });
      });

    return () => {
      cancelled = true;
    };
  }, [rec]);

  // Close on Escape, and lock background scroll while open.
  useEffect(() => {
    if (!rec) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [rec, onClose]);

  if (!rec) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/60 p-4 backdrop-blur-md"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`${rec.title} trailer`}
    >
      <div
        className="relative w-full max-w-3xl overflow-hidden rounded-3xl bg-surface shadow-card"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 px-5 py-3.5">
          <h2 className="truncate text-lg font-semibold tracking-tight text-ink">
            {rec.title}
            {rec.year ? <span className="ml-2 text-sm font-normal text-muted">{rec.year}</span> : null}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close trailer"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-surface-2 text-ink transition hover:brightness-95"
          >
            ✕
          </button>
        </div>

        <div className="relative aspect-video w-full bg-black">
          {phase.state === 'loading' && (
            <div className="absolute inset-0 flex items-center justify-center">
              <p className="animate-pulse text-white/70">Loading trailer…</p>
            </div>
          )}

          {phase.state === 'playing' && (
            <iframe
              className="absolute inset-0 h-full w-full"
              // playsinline keeps iOS from forcing its native fullscreen player;
              // mute lets it actually autostart (iOS blocks autoplay with sound
              // when the load isn't in the tap's synchronous call stack) — the
              // viewer taps the speaker to unmute.
              src={`https://www.youtube-nocookie.com/embed/${phase.key}?autoplay=1&mute=1&playsinline=1&rel=0&modestbranding=1`}
              title={`${rec.title} trailer`}
              allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
              allowFullScreen
            />
          )}

          {phase.state === 'unavailable' && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center">
              <p className="text-white/70">No in-app trailer available for this title.</p>
              <a
                href={youtubeTrailerUrl(rec.title, rec.year)}
                target="_blank"
                rel="noopener noreferrer"
                className="rounded-full bg-accent px-4 py-2 text-sm font-medium text-white transition hover:brightness-110"
              >
                Search on YouTube ↗
              </a>
            </div>
          )}
        </div>

        {rec.overview && (
          <p className="max-h-32 overflow-y-auto px-5 py-4 text-sm leading-relaxed text-ink/80">{rec.overview}</p>
        )}
      </div>
    </div>
  );
}
