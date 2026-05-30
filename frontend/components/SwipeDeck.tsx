'use client';

import { AnimatePresence } from 'framer-motion';
import { useCallback, useEffect, useRef, useState } from 'react';

import { recordSwipe } from '@/lib/api';
import { KEY_TO_ACTION } from '@/lib/actions';
import type { DeckApi } from '@/lib/deck';
import type { Recommendation, SwipeAction } from '@/lib/types';
import { makeSessionId } from '@/lib/util';
import ActionBar from './ActionBar';
import KeyHints from './KeyHints';
import SwipeCard from './SwipeCard';

interface SwipeDeckProps {
  deck: DeckApi;
  onOpenCard: (rec: Recommendation) => void;
}

export default function SwipeDeck({ deck, onOpenCard }: SwipeDeckProps) {
  const sessionIdRef = useRef<string>('');
  const lockedRef = useRef(false);
  const appearedAtRef = useRef<number>(0);
  const wheelAccum = useRef({ x: 0, y: 0, t: 0 });
  const wheelLock = useRef(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const [exitAction, setExitAction] = useState<SwipeAction | null>(null);
  const [hintsVisible, setHintsVisible] = useState(true);
  const [expanded, setExpanded] = useState(false);

  const threshold = typeof window !== 'undefined' && window.matchMedia?.('(pointer: coarse)').matches ? 120 : 100;

  // Assign a session id once on the client (avoids SSR hydration mismatch).
  useEffect(() => {
    if (!sessionIdRef.current) sessionIdRef.current = makeSessionId();
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
      lockedRef.current = true;
      setExitAction(action);
      if (typeof navigator !== 'undefined' && navigator.vibrate) navigator.vibrate(12);

      const elapsed = Date.now() - appearedAtRef.current;
      if (res.card.tmdb_id != null) {
        recordSwipe({
          session_id: sessionIdRef.current || 'anon',
          tmdb_id: res.card.tmdb_id,
          action,
          time_on_card_ms: elapsed,
          remaining: res.remaining,
        })
          .then((r) => deck.reorderRemaining(r.reranked_queue))
          .catch(() => {
            /* re-ranking is a non-critical enhancement — ignore failures */
          });
      }
    },
    [deck],
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

  const cards = deck.currentCard ? [deck.currentCard, ...deck.upcoming] : [];

  return (
    <div ref={containerRef} className="flex h-full w-full flex-col">
      <div className="relative mx-auto w-full max-w-[420px] flex-1" style={{ minHeight: 520 }}>
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
              onOpen={i === 0 ? () => onOpenCard(rec) : undefined}
            />
          ))}
        </AnimatePresence>
        <KeyHints visible={hintsVisible} />
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
