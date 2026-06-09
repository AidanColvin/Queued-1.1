'use client';

import { AnimatePresence, motion } from 'framer-motion';

interface KeyHintsProps {
  visible: boolean;
}

/** Subtle keyboard-hint overlay shown on first load, fades after 3s / first key. */
export default function KeyHints({ visible }: KeyHintsProps) {
  const hints: [string, string][] = [
    ['A / ←', 'Dislike'],
    ['W / ↑', 'Watchlist'],
    ['S / ↓', 'Not seen'],
    ['D / →', 'Like'],
  ];
  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.4 }}
          className="pointer-events-none absolute inset-x-0 bottom-3 flex flex-wrap justify-center gap-2 px-3 text-[11px] text-white/80"
        >
          {hints.map(([key, label]) => (
            <span key={key} className="rounded-md bg-black/45 px-2 py-1 backdrop-blur-md">
              <span className="font-semibold text-white">{key}</span> {label}
            </span>
          ))}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
