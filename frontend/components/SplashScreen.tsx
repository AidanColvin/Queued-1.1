'use client';

import { useEffect, useState } from 'react';

type Phase = 'static' | 'title' | 'fading';

/**
 * Retro-TV intro splash shown on every full page load / hard refresh: a CRT
 * showing static for ~1s, then the screen "turns on" to white and shows the
 * lowercase wordmark for ~1.8s, then the whole thing fades into the app. Tap
 * anywhere to skip. Purely decorative — sits above everything and removes
 * itself when done.
 */
export default function SplashScreen() {
  const [phase, setPhase] = useState<Phase>('static');
  const [gone, setGone] = useState(false);

  useEffect(() => {
    const timers = [
      window.setTimeout(() => setPhase('title'), 1200),
      window.setTimeout(() => setPhase('fading'), 3000),
      window.setTimeout(() => setGone(true), 3600),
    ];
    return () => timers.forEach(clearTimeout);
  }, []);

  if (gone) return null;

  const skip = () => {
    setPhase('fading');
    window.setTimeout(() => setGone(true), 500);
  };

  const lit = phase !== 'static'; // screen has "turned on" to the wordmark

  return (
    <div
      aria-hidden
      onClick={skip}
      className={`fixed inset-0 z-[100] flex items-center justify-center ${
        lit ? 'bg-white' : 'bg-black'
      } ${phase === 'fading' ? 'opacity-0' : 'opacity-100'}`}
      style={{ transition: 'opacity 0.55s ease, background-color 0.45s ease' }}
    >
      <div className={`relative transition-transform duration-500 ${phase === 'fading' ? 'scale-105' : 'scale-100'}`}>
        {/* Rabbit-ear antennas */}
        <div className="absolute -top-10 left-1/2 -z-10 h-12 w-px origin-bottom -translate-x-1/2 -rotate-[28deg] bg-[#555]" />
        <div className="absolute -top-10 left-1/2 -z-10 h-12 w-px origin-bottom -translate-x-1/2 rotate-[28deg] bg-[#555]" />
        <div className="absolute -top-[42px] left-1/2 -z-10 h-1.5 w-1.5 -translate-x-[14px] rounded-full bg-[#666]" />
        <div className="absolute -top-[42px] left-1/2 -z-10 h-1.5 w-1.5 translate-x-[8px] rounded-full bg-[#666]" />

        {/* TV body */}
        <div className="flex items-stretch gap-3 rounded-[2rem] bg-gradient-to-b from-[#3c3c40] to-[#202023] p-4 shadow-[0_30px_80px_-20px_rgba(0,0,0,0.7)] ring-1 ring-white/10">
          {/* Screen */}
          <div className="relative h-52 w-72 overflow-hidden rounded-2xl bg-black ring-1 ring-black/60 sm:h-56 sm:w-80">
            {lit ? (
              <div className="absolute inset-0 flex items-center justify-center bg-white">
                <span className="animate-fade-in text-2xl font-semibold lowercase tracking-tight text-ink sm:text-3xl">
                  next watch
                </span>
              </div>
            ) : (
              <>
                <div className="tv-static absolute inset-0 opacity-90" />
                <div className="tv-scanlines absolute inset-0" />
                {/* CRT curvature vignette */}
                <div className="absolute inset-0 shadow-[inset_0_0_60px_20px_rgba(0,0,0,0.55)]" />
              </>
            )}
          </div>

          {/* Control strip: two knobs + a speaker grille */}
          <div className="flex w-10 flex-col items-center justify-center gap-3">
            <div className="h-6 w-6 rounded-full bg-[#0c0c0d] ring-2 ring-white/10" />
            <div className="h-6 w-6 rounded-full bg-[#0c0c0d] ring-2 ring-white/10" />
            <div className="mt-1 flex flex-col gap-[3px]">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="h-px w-6 bg-white/15" />
              ))}
            </div>
            {/* Power LED — red while static, green once lit */}
            <div className={`h-1.5 w-1.5 rounded-full ${lit ? 'bg-like' : 'bg-pass'}`} />
          </div>
        </div>
      </div>
    </div>
  );
}
