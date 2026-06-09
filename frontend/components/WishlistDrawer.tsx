'use client';

import { AnimatePresence, motion } from 'framer-motion';

import { useCardPoster } from '@/lib/posters';
import type { Recommendation } from '@/lib/types';
import { youtubeTrailerUrl } from '@/lib/util';

interface WishlistDrawerProps {
  open: boolean;
  items: Recommendation[];
  onClose: () => void;
}

/** A single saved title — resolves a keyless poster when the dataset lacks one. */
function WishlistRow({ rec }: { rec: Recommendation }) {
  const poster = useCardPoster(rec);
  return (
    <a
      href={youtubeTrailerUrl(rec.title, rec.year)}
      target="_blank"
      rel="noreferrer"
      className="flex gap-3 rounded-xl p-2 transition hover:bg-surface-2"
    >
      <div className="flex h-20 w-14 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-surface-2">
        {poster ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={poster} alt={rec.title} className="h-full w-full object-cover" />
        ) : (
          <span className="text-lg">🎬</span>
        )}
      </div>
      <div className="min-w-0 self-center">
        <p className="truncate font-medium text-ink">{rec.title}</p>
        <p className="text-xs text-muted">
          {rec.year ?? ''}
          {rec.genres.length ? ` · ${rec.genres.slice(0, 2).join(', ')}` : ''}
        </p>
        {rec.cast.length > 0 && <p className="mt-0.5 truncate text-xs text-faint">{rec.cast.join(' · ')}</p>}
      </div>
    </a>
  );
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
            className="fixed right-0 top-0 z-50 flex h-full w-[88vw] max-w-sm flex-col bg-surface shadow-card"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 320, damping: 34 }}
          >
            <div className="flex items-center justify-between border-b border-hairline px-5 py-4">
              <h2 className="text-xl font-semibold tracking-tight text-ink">Watchlist</h2>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close watchlist"
                className="flex h-8 w-8 items-center justify-center rounded-full text-muted transition hover:bg-surface-2 hover:text-ink"
              >
                ✕
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              {items.length === 0 ? (
                <p className="mt-12 text-center text-sm text-muted">
                  Swipe <span className="font-medium text-save">up ↑</span> on a title to save it here.
                </p>
              ) : (
                <ul className="space-y-2">
                  {items
                    .slice()
                    .reverse()
                    .map((rec) => (
                      <li key={rec.id}>
                        <WishlistRow rec={rec} />
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
