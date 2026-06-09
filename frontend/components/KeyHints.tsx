'use client';

import { AnimatePresence, motion } from 'framer-motion';

interface KeyHintsProps {
  visible: boolean;
}

/** Subtle keyboard-hint overlay shown on first load, fades after 3s / first key. */
export default function KeyHints({ visible }: KeyHintsProps) {
  const hints: [string, string, string][] = [
    ['←', 'Pass', '#ff5e5b'],
    ['↑', 'Save', '#4aa8ff'],
    ['↓', 'Unseen', '#8a9099'],
    ['→', 'Like', '#3ecf8e'],
  ];
  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.4 }}
          className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center gap-2 text-[11px]"
        >
          {hints.map(([key, label, color]) => (
            <span
              key={label}
              className="flex items-center gap-1.5 rounded-full border border-white/10 bg-black/50 px-2.5 py-1 backdrop-blur-md"
            >
              <span className="text-base font-bold leading-none" style={{ color }}>
                {key}
              </span>
              <span className="text-white/75">{label}</span>
            </span>
          ))}
        </motion.div>
      )}
    </AnimatePresence>
  );
}
