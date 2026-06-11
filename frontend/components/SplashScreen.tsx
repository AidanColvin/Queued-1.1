'use client';

import { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'framer-motion';

type Phase = 'writing' | 'hold' | 'fading';

/**
 * Wordmark intro shown on every full page load / hard refresh. The word
 * "Queued" writes itself out left-to-right, starting from the Q, with a
 * hairline caret riding the leading edge; it then fades up into the app. Tap
 * anywhere to skip. Calm, monochrome, Apple-style — purely decorative, and it
 * removes itself from the tree once done.
 */
export default function SplashScreen() {
  const reduce = useReducedMotion();
  const [phase, setPhase] = useState<Phase>('writing');
  const [gone, setGone] = useState(false);

  // The whole word is written over this window (instant for reduced motion).
  const writeMs = reduce ? 0 : 1400;

  useEffect(() => {
    const timers = [
      window.setTimeout(() => setPhase('hold'), writeMs + 120),
      window.setTimeout(() => setPhase('fading'), writeMs + 680),
      window.setTimeout(() => setGone(true), writeMs + 1320),
    ];
    return () => timers.forEach(clearTimeout);
  }, [writeMs]);

  if (gone) return null;

  const skip = () => {
    setPhase('fading');
    window.setTimeout(() => setGone(true), 600);
  };

  // Soft "ease-out-expo" — quick to start, gentle to settle, like a pen lift.
  const ease = [0.22, 1, 0.36, 1] as const;

  return (
    <motion.div
      aria-hidden
      onClick={skip}
      className="fixed inset-0 z-[100] flex items-center justify-center bg-canvas"
      initial={{ opacity: 1 }}
      animate={{ opacity: phase === 'fading' ? 0 : 1, scale: phase === 'fading' ? 1.04 : 1 }}
      transition={{ duration: 0.6, ease }}
    >
      <div className="relative inline-block text-6xl font-semibold tracking-tight text-ink sm:text-7xl">
        {/* The word, unveiled left-to-right like a single pen stroke. */}
        <motion.div
          className="overflow-hidden"
          initial={{ clipPath: reduce ? 'inset(0 0 0 0)' : 'inset(0 100% 0 0)' }}
          animate={{ clipPath: 'inset(0 0 0 0)' }}
          transition={{ duration: writeMs / 1000, ease }}
        >
          <span className="block leading-none">Queued</span>
        </motion.div>

        {/* Hairline caret that rides the writing edge, then quietly lifts off. */}
        {!reduce && (
          <motion.span
            className="absolute top-1/2 h-[0.78em] w-[2px] -translate-y-1/2 rounded-full bg-ink"
            initial={{ left: '0%', opacity: 1 }}
            animate={
              phase === 'writing' ? { left: '100%', opacity: 1 } : { left: '100%', opacity: 0 }
            }
            transition={
              phase === 'writing'
                ? { duration: writeMs / 1000, ease }
                : { duration: 0.45, ease: 'easeOut' }
            }
          />
        )}
      </div>
    </motion.div>
  );
}
