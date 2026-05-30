'use client';

import { AnimatePresence, motion } from 'framer-motion';

import type { Recommendation } from '@/lib/types';
import { youtubeTrailerUrl } from '@/lib/util';

interface WishlistDrawerProps {
  open: boolean;
  items: Recommendation[];
  onClose: () => void;
}

/** Slide-over list of the titles the user swiped up (their wish list). */
export default function WishlistDrawer({ open, items, onClose }: WishlistDrawerProps) {
  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            className="fixed inset-0 z-40 bg-black/60"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />
          <motion.aside
            className="fixed right-0 top-0 z-50 flex h-full w-[88vw] max-w-sm flex-col border-l border-warm bg-surface"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 320, damping: 34 }}
          >
            <div className="flex items-center justify-between border-b border-white/10 p-4">
              <h2 className="font-serif text-2xl text-ink">Watchlist</h2>
              <button type="button" onClick={onClose} aria-label="Close watchlist" className="text-muted hover:text-ink">
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              {items.length === 0 ? (
                <p className="mt-10 text-center text-sm text-muted">
                  Swipe <span className="text-save">up ↑</span> on a title to save it here.
                </p>
              ) : (
                <ul className="space-y-3">
                  {items
                    .slice()
                    .reverse()
                    .map((rec) => (
                      <li key={rec.id}>
                        <a
                          href={youtubeTrailerUrl(rec.title, rec.year)}
                          target="_blank"
                          rel="noreferrer"
                          className="flex gap-3 rounded-lg border border-white/10 p-2 transition hover:border-amber"
                        >
                          <div className="h-20 w-14 shrink-0 overflow-hidden rounded bg-gradient-to-br from-surface-2 to-black">
                            {rec.poster_url ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img src={rec.poster_url} alt={rec.title} className="h-full w-full object-cover" />
                            ) : null}
                          </div>
                          <div className="min-w-0">
                            <p className="truncate text-ink">{rec.title}</p>
                            <p className="text-xs text-muted">
                              {rec.year ?? ''} · {rec.genres.slice(0, 2).join(', ')}
                            </p>
                            {rec.cast.length > 0 && (
                              <p className="mt-0.5 truncate text-xs text-white/50">{rec.cast.join(' · ')}</p>
                            )}
                          </div>
                        </a>
                      </li>
                    ))}
                </ul>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
