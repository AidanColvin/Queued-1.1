'use client';

import { AnimatePresence, motion } from 'framer-motion';

import type { Recommendation } from '@/lib/types';
import { youtubeTrailerUrl } from '@/lib/util';
import { PlayIcon, XIcon } from './Icons';

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
            className="fixed right-0 top-0 z-50 flex h-full w-[88vw] max-w-sm flex-col border-l border-black/10 bg-paper shadow-card"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 320, damping: 34 }}
          >
            <div className="flex items-center justify-between border-b border-black/10 p-4">
              <div className="flex items-baseline gap-2">
                <h2 className="font-serif text-2xl text-graphite">Watchlist</h2>
                {items.length > 0 && (
                  <span className="text-sm tabular-nums text-slate">{items.length}</span>
                )}
              </div>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close watchlist"
                className="flex h-9 w-9 items-center justify-center rounded-full border border-black/10 text-slate transition hover:border-amber hover:text-graphite"
              >
                <XIcon className="h-5 w-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              {items.length === 0 ? (
                <p className="mt-10 text-center text-sm text-slate">
                  Swipe <span className="font-medium text-save">up</span> on a title to save it here.
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
                          className="group flex items-center gap-3 rounded-xl border border-black/10 bg-cloud p-2 transition hover:border-amber hover:bg-cloud-2"
                        >
                          <div className="relative h-20 w-14 shrink-0 overflow-hidden rounded-lg bg-gradient-to-br from-cloud-2 to-cloud">
                            {rec.poster_url ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img src={rec.poster_url} alt={rec.title} className="h-full w-full object-cover" />
                            ) : null}
                            <span className="absolute inset-0 flex items-center justify-center bg-black/50 text-white opacity-0 transition group-hover:opacity-100">
                              <PlayIcon className="h-6 w-6" />
                            </span>
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="truncate font-medium text-graphite">{rec.title}</p>
                            <p className="text-xs text-slate">
                              {rec.year ?? ''} · {rec.genres.slice(0, 2).join(', ')}
                            </p>
                            {rec.cast.length > 0 && (
                              <p className="mt-0.5 truncate text-xs text-slate/70">{rec.cast.join(' · ')}</p>
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
