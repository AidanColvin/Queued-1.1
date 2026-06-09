'use client';

import {
  motion,
  useMotionValue,
  useTransform,
  type MotionValue,
  type PanInfo,
} from 'framer-motion';
import { useRef, useState, type PointerEvent as ReactPointerEvent } from 'react';

import { ACTION_CONFIG } from '@/lib/actions';
import type { Recommendation, SwipeAction } from '@/lib/types';
import ScoreBar from './ScoreBar';

interface SwipeCardProps {
  rec: Recommendation;
  depth: number; // 0 = top (interactive), 1, 2 peek behind
  isTop: boolean;
  threshold: number;
  expanded: boolean;
  onCommit: (action: SwipeAction) => void;
  onOpen?: () => void;
}

/** Decide which action a drag offset represents (dominant axis wins). */
function actionForOffset(offset: { x: number; y: number }, threshold: number): SwipeAction | null {
  const ax = Math.abs(offset.x);
  const ay = Math.abs(offset.y);
  if (Math.max(ax, ay) < threshold) return null;
  if (ax > ay) return offset.x > 0 ? 'liked' : 'dismissed';
  return offset.y < 0 ? 'saved' : 'skip';
}

/** Dynamic exit variant — receives the committed action via AnimatePresence custom.
 *  A short tween (not a slow spring) so the card clears fast and the next swipe
 *  is accepted almost immediately — rapid swiping never feels dropped. */
const cardVariants = {
  exit: (action: SwipeAction | null) =>
    action
      ? {
          ...ACTION_CONFIG[action].exit,
          opacity: 0,
          transition: {
            duration: 0.22,
            ease: 'easeOut',
            // Hold the card fully opaque while it slides clear of the deck, then
            // cut its opacity only at the very end. A leaving card must never be
            // semi-transparent over the card behind it — that cross-fade is what
            // made posters look see-through and made one swipe look like two
            // cards moving at once.
            opacity: { delay: 0.2, duration: 0.02 },
          },
        }
      : { opacity: 0, scale: 0.9, transition: { duration: 0.18 } },
};

/** A bold, tilted stamp (LIKE / PASS / SAVE / SKIP) revealed while dragging. */
function Stamp({ action, opacity }: { action: SwipeAction; opacity: MotionValue<number> }) {
  const cfg = ACTION_CONFIG[action];
  return (
    <motion.div
      style={{ opacity, color: cfg.color, borderColor: cfg.color }}
      className="pointer-events-none absolute left-6 top-6 -rotate-12 rounded-md border-4 px-4 py-1 text-3xl font-extrabold tracking-widest"
    >
      {cfg.label}
    </motion.div>
  );
}

export default function SwipeCard({
  rec,
  depth,
  isTop,
  threshold,
  expanded,
  onCommit,
  onOpen,
}: SwipeCardProps) {
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const rotate = useTransform(x, [-320, 320], [-16, 16]);
  const tint = useTransform([x, y], ([lx, ly]: number[]) => {
    const ax = Math.abs(lx);
    const ay = Math.abs(ly);
    if (Math.max(ax, ay) < 8) return 'rgba(0,0,0,0)';
    const color =
      ax > ay
        ? lx > 0
          ? ACTION_CONFIG.liked.color
          : ACTION_CONFIG.dismissed.color
        : ly < 0
          ? ACTION_CONFIG.saved.color
          : ACTION_CONFIG.skip.color;
    const o = Math.min(Math.max(ax, ay) / threshold, 1) * 0.32;
    return `${color}${Math.round(o * 255).toString(16).padStart(2, '0')}`;
  });

  const likeOpacity = useTransform(x, [0, threshold], [0, 0.85]);
  const passOpacity = useTransform(x, [0, -threshold], [0, 0.85]);
  const saveOpacity = useTransform(y, [0, -threshold], [0, 0.85]);
  const skipOpacity = useTransform(y, [0, threshold], [0, 0.85]);

  const [imgFailed, setImgFailed] = useState(false);
  const hasPoster = rec.poster_url && !imgFailed;

  // Distinguish a tap (open trailer) from a swipe (commit a decision) from the
  // raw pointer positions rather than framer's `onTap` — which fires on
  // pointer-up even after a drag and would otherwise open YouTube on every
  // swipe. We record where the press began and, on release, only treat it as a
  // tap if the pointer barely moved. Any real drag is left entirely to
  // `onDragEnd` and never opens the trailer.
  const pressRef = useRef<{ x: number; y: number } | null>(null);

  const scale = 1 - depth * 0.05;
  const offsetY = depth * 14;

  return (
    <motion.div
      className="absolute inset-0 mx-auto w-full max-w-[420px] select-none"
      style={isTop ? { x, y, rotate, zIndex: 30, touchAction: 'none' } : { zIndex: 30 - depth }}
      drag={isTop}
      dragSnapToOrigin
      dragElastic={0.55}
      onPointerDown={
        isTop
          ? (e: ReactPointerEvent) => {
              pressRef.current = { x: e.clientX, y: e.clientY };
            }
          : undefined
      }
      onPointerUp={
        isTop
          ? (e: ReactPointerEvent) => {
              const start = pressRef.current;
              pressRef.current = null;
              if (!start) return;
              const moved = Math.hypot(e.clientX - start.x, e.clientY - start.y);
              // Under ~10px of travel = a tap → open the trailer + expand.
              // Anything more is a swipe and is handled solely by onDragEnd.
              if (moved < 10) onOpen?.();
            }
          : undefined
      }
      onDragEnd={(_e: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => {
        const action = actionForOffset(info.offset, threshold);
        if (action) onCommit(action);
      }}
      variants={cardVariants}
      // Cards behind the top stay fully opaque — they slide/scale into place but
      // never fade in. A peek card fading from transparent reads as a second
      // ghosted poster behind the current one.
      //
      // `opacity: 1` is asserted on every visible card's `animate` target on
      // purpose: if a swipe interrupts a card's entrance, framer freezes any
      // property that's missing from the next target at its mid-flight value.
      // Without opacity here, a card caught mid-fade would stay permanently
      // semi-transparent at rest, letting the poster behind it show through.
      // Naming it guarantees framer always drives it back to fully opaque.
      initial={isTop ? false : { scale: scale - 0.04, y: offsetY + 10, opacity: 1 }}
      animate={isTop ? { scale: 1, opacity: 1 } : { scale, y: offsetY, opacity: 1 }}
      exit="exit"
      transition={{ type: 'spring', stiffness: 300, damping: 26 }}
    >
      <div className="group relative h-full w-full overflow-hidden rounded-2xl border border-warm bg-surface shadow-[0_10px_40px_-12px_rgba(0,0,0,0.7)]">
        {hasPoster ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={rec.poster_url as string}
            alt={`${rec.title} poster`}
            loading="lazy"
            draggable={false}
            onError={() => setImgFailed(true)}
            className="absolute inset-0 h-full w-full object-cover"
          />
        ) : (
          <div className="absolute inset-0 bg-gradient-to-br from-surface-2 via-charcoal to-black">
            <div className="flex h-full items-center justify-center p-8">
              <span className="text-center font-serif text-3xl text-white/25">{rec.title}</span>
            </div>
          </div>
        )}

        <div className="absolute inset-x-0 bottom-0 h-[55%] bg-gradient-to-t from-black via-black/80 to-transparent" />

        {isTop && (
          <>
            <motion.div className="pointer-events-none absolute inset-0" style={{ backgroundColor: tint }} />
            <Stamp action="liked" opacity={likeOpacity} />
            <Stamp action="dismissed" opacity={passOpacity} />
            <Stamp action="saved" opacity={saveOpacity} />
            <Stamp action="skip" opacity={skipOpacity} />
          </>
        )}

        <div className="absolute inset-x-0 bottom-0 space-y-1.5 p-5">
          <h2 className="font-serif text-3xl leading-tight text-ink drop-shadow">{rec.title}</h2>
          <div className="flex flex-wrap gap-1.5">
            {rec.year ? (
              <span className="rounded-full bg-white/10 px-2 py-0.5 text-[11px] text-white/70">{rec.year}</span>
            ) : null}
            {rec.genres.slice(0, 3).map((g) => (
              <span key={g} className="rounded-full bg-white/10 px-2 py-0.5 text-[11px] text-white/70">
                {g}
              </span>
            ))}
          </div>
          {rec.cast.length > 0 && (
            <p className="truncate text-xs text-white/70">{rec.cast.join(' · ')}</p>
          )}
          {rec.overview && (
            <p className={`text-sm text-white/80 ${expanded ? '' : 'line-clamp-2'}`}>{rec.overview}</p>
          )}
          {expanded && rec.why && <p className="text-xs italic text-amber/90">{rec.why}</p>}
          <div className="pt-1.5">
            <ScoreBar score={rec.score} />
          </div>
        </div>
      </div>
    </motion.div>
  );
}
