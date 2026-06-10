'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { useCallback, useEffect, useRef, useState } from 'react';

import { recordSwipe } from '@/lib/api';
import { KEY_TO_ACTION } from '@/lib/actions';
import { hapticImpact } from '@/lib/native';
import type { DeckApi } from '@/lib/deck';
import type { ProviderPrefs, Recommendation, SwipeAction } from '@/lib/types';
import { getSessionId } from '@/lib/util';
import ActionBar from './ActionBar';
import KeyHints from './KeyHints';
import SwipeCard from './SwipeCard';

interface SwipeDeckProps {
  deck: DeckApi;
  onOpenCard: (rec: Recommendation) => void;
  /** Persist a committed liked/saved card to the signed-in account (no-op for
   *  guests). Fire-and-forget, like the swipe recording itself. */
  onPersistSave?: (rec: Recommendation, action: SwipeAction) => void;
  /** The streaming filter in effect — sent with each swipe so the server-side
   *  re-rank can softly boost on-service titles in "prefer" mode. */
  providerPrefs?: ProviderPrefs;
}

export default function SwipeDeck({ deck, onOpenCard, onPersistSave, providerPrefs }: SwipeDeckProps) {
  const sessionIdRef = useRef<string>('');
  const lockedRef = useRef(false);
  const appearedAtRef = useRef<number>(0);
  const wheelAccum = useRef({ x: 0, y: 0, t: 0 });
  const wheelLock = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const [exitAction, setExitAction] = useState<SwipeAction | null>(null);
  const [hintsVisible, setHintsVisible] = useState(true);
  const [expanded, setExpanded] = useState(false);
  // Bumped on every super like so the celebratory ★ flash re-plays each time.
  const [superFlash, setSuperFlash] = useState(0);

  const threshold = typeof window !== 'undefined' && window.matchMedia?.('(pointer: coarse)').matches ? 120 : 100;

  // Use the persisted anonymous session id (shared with the adaptive deck), set
  // on the client to avoid an SSR hydration mismatch.
  useEffect(() => {
    if (!sessionIdRef.current) sessionIdRef.current = getSessionId();
    appearedAtRef.current = Date.now();
  }, []);

  // Reset the deliberation timer and collapse details when the top card changes.
  const topId = deck.currentCard?.tmdb_id ?? null;
  useEffect(() => {
    appearedAtRef.current = Date.now();
    setExpanded(false);
  }, [topId]);

  // Fade the key hints after 3 seconds.
  useEffect(() => {
    const t = setTimeout(() => setHintsVisible(false), 3000);
    return () => clearTimeout(t);
  }, []);

  const decide = useCallback(
    (action: SwipeAction) => {
      if (lockedRef.current) return;
      const res = deck.commit(action);
      if (!res) return;
      // Mirror a like/save to the signed-in account (no-op for guests).
      onPersistSave?.(res.card, action);
      lockedRef.current = true;
      setExitAction(action);
      if (action === 'superliked') setSuperFlash((n) => n + 1);
      // Safety net: release the input lock shortly after the exit tween even if
      // AnimatePresence's onExitComplete is delayed or never fires, so the deck
      // can never get stuck "unable to swipe".
      window.setTimeout(() => {
        lockedRef.current = false;
      }, 260);
      // A super like gets a stronger double-buzz than an ordinary swipe.
      // Native (Capacitor) builds get real impact haptics; web falls back to
      // navigator.vibrate where available.
      void hapticImpact(action === 'superliked');

      const elapsed = Date.now() - appearedAtRef.current;
      if (res.card.tmdb_id != null) {
        recordSwipe({
          session_id: sessionIdRef.current || 'anon',
          tmdb_id: res.card.tmdb_id,
          action,
          time_on_card_ms: elapsed,
          remaining: res.remaining,
          ...(providerPrefs && providerPrefs.filter !== 'all'
            ? { provider_filter: providerPrefs.filter, providers: providerPrefs.providers }
            : {}),
        })
          .then((r) => deck.reorderRemaining(r.reranked_queue))
          .catch(() => {
            /* re-ranking is a non-critical enhancement — ignore failures */
          });
      }
    },
    [deck, onPersistSave, providerPrefs],
  );

  // Keyboard: WASD + arrows, Z/Backspace undo, Space expand. Ignored in inputs.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable)) return;
      const key = e.key.toLowerCase();
      if (key === 'z' || key === 'backspace') {
        e.preventDefault();
        setHintsVisible(false);
        deck.undo();
        return;
      }
      if (key === ' ' || key === 'spacebar') {
        e.preventDefault();
        setHintsVisible(false);
        setExpanded((v) => !v);
        return;
      }
      const action = KEY_TO_ACTION[key];
      if (action) {
        e.preventDefault();
        setHintsVisible(false);
        decide(action);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [deck, decide]);

  // Trackpad: a two-finger swipe sends the card the way your fingers move, in
  // all four directions. macOS "natural" scrolling (the default) reports a
  // finger-right swipe as NEGATIVE deltaX and a finger-up swipe as POSITIVE
  // deltaY, so the card follows the finger when we map it this way. A firm
  // threshold + cooldown keeps incidental scrolling from committing a swipe.
  useEffect(() => {
    const node = containerRef.current;
    if (!node) return;
    const THRESHOLD = 120;
    const onWheel = (e: WheelEvent) => {
      if (wheelLock.current || lockedRef.current) return;
      const now = Date.now();
      const acc = wheelAccum.current;
      if (now - acc.t > 120) {
        acc.x = 0;
        acc.y = 0;
      }
      acc.x += e.deltaX;
      acc.y += e.deltaY;
      acc.t = now;
      const adx = Math.abs(acc.x);
      const ady = Math.abs(acc.y);
      if (Math.max(adx, ady) < THRESHOLD) return;
      // Finger-right (deltaX<0) → like; finger-up (deltaY>0) → save.
      const action: SwipeAction =
        adx > ady ? (acc.x < 0 ? 'liked' : 'dismissed') : acc.y > 0 ? 'saved' : 'skip';
      acc.x = 0;
      acc.y = 0;
      wheelLock.current = true;
      setHintsVisible(false);
      window.setTimeout(() => {
        wheelLock.current = false;
      }, 500);
      decide(action);
    };
    node.addEventListener('wheel', onWheel, { passive: true });
    return () => node.removeEventListener('wheel', onWheel);
  }, [decide]);

  // Tapping the top card both reveals the full synopsis/why inline and opens the
  // trailer in the browser — a click is "tell me more + play it", a swipe is a
  // decision (handled separately, and never triggers this).
  const openTopCard = useCallback(
    (rec: Recommendation) => {
      setExpanded(true);
      onOpenCard(rec);
    },
    [onOpenCard],
  );

  const cards = deck.currentCard ? [deck.currentCard, ...deck.upcoming] : [];

  return (
    <div ref={containerRef} className="flex h-full w-full flex-col">
      {/* Center a poster-proportioned (2:3) card in the available space so the
          poster shows in its natural shape instead of being cropped to fill a
          full-height box. */}
      <div className="flex min-h-0 flex-1 items-center justify-center">
        <div className="relative aspect-[2/3] max-h-full w-full max-w-[420px]">
        <AnimatePresence
          custom={exitAction}
          onExitComplete={() => {
            lockedRef.current = false;
            setExitAction(null);
            appearedAtRef.current = Date.now();
          }}
        >
          {cards.map((rec, i) => (
            <SwipeCard
              key={rec.id}
              rec={rec}
              depth={i}
              isTop={i === 0}
              threshold={threshold}
              expanded={i === 0 && expanded}
              onCommit={decide}
              onOpen={i === 0 ? () => openTopCard(rec) : undefined}
              onSuperLike={i === 0 ? () => decide('superliked') : undefined}
            />
          ))}
        </AnimatePresence>

          <SuperLikeFlash trigger={superFlash} />
          <KeyHints visible={hintsVisible} />
        </div>
      </div>

      <div className="mx-auto mt-5 w-full max-w-[460px]">
        <ActionBar
          swiped={deck.decisionsCount}
          canUndo={deck.canUndo}
          onAction={decide}
          onUndo={() => deck.undo()}
          onToggleDetails={() => setExpanded((v) => !v)}
        />
      </div>
    </div>
  );
}

/** A celebratory gold ★ that pops and fades over the deck on each super like.
 *  Keyed on `trigger` (a counter) so it re-mounts and re-plays every time; the
 *  keyframe animation fades itself out, so it leaves nothing on screen. */
function SuperLikeFlash({ trigger }: { trigger: number }) {
  if (trigger === 0) return null;
  return (
    <motion.div
      key={trigger}
      className="pointer-events-none absolute inset-0 z-50 flex items-center justify-center"
      initial={{ opacity: 0, scale: 0.4 }}
      animate={{ opacity: [0, 1, 1, 0], scale: [0.4, 1, 1.05, 1.6] }}
      transition={{ duration: 0.6, ease: 'easeOut', times: [0, 0.25, 0.6, 1] }}
    >
      <span
        className="text-8xl drop-shadow-[0_4px_24px_rgba(255,214,10,0.7)]"
        style={{ color: '#ffd60a' }}
      >
        ★
      </span>
    </motion.div>
  );
}
