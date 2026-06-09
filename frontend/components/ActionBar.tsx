'use client';

import type { ComponentType } from 'react';

import { ACTION_CONFIG } from '@/lib/actions';
import type { SwipeAction } from '@/lib/types';
import { BookmarkIcon, EyeOffIcon, HeartIcon, InfoIcon, UndoIcon, XIcon } from './Icons';

interface ActionBarProps {
  swiped: number;
  canUndo: boolean;
  onAction: (action: SwipeAction) => void;
  onUndo: () => void;
  onToggleDetails: () => void;
}

// Icon + relative emphasis per action. Like/Dislike are the primary calls and
// get the larger, brighter buttons; Watchlist/Not-seen are the secondary pair.
const ACTION_META: Record<SwipeAction, { Icon: ComponentType<{ className?: string }>; primary: boolean }> = {
  dismissed: { Icon: XIcon, primary: true },
  skip: { Icon: EyeOffIcon, primary: false },
  saved: { Icon: BookmarkIcon, primary: false },
  liked: { Icon: HeartIcon, primary: true },
};

// Reorder so the two primary actions bookend the secondary pair:
//   ✕ dislike · 🙈 not-seen · 🔖 watchlist · ♥ like
const ORDER: SwipeAction[] = ['dismissed', 'skip', 'saved', 'liked'];

export default function ActionBar({
  swiped,
  canUndo,
  onAction,
  onUndo,
  onToggleDetails,
}: ActionBarProps) {
  return (
    <div className="flex items-center justify-center gap-2.5 sm:gap-4">
      <button
        type="button"
        onClick={onUndo}
        disabled={!canUndo}
        className="flex h-11 w-11 items-center justify-center rounded-full border border-white/10 bg-surface/80 text-muted shadow-card transition enabled:hover:scale-105 enabled:hover:border-warm enabled:hover:text-ink enabled:active:scale-95 disabled:opacity-25"
        aria-label="Undo last swipe"
        title="Undo"
      >
        <UndoIcon className="h-5 w-5" />
      </button>

      {ORDER.map((action) => {
        const cfg = ACTION_CONFIG[action];
        const { Icon, primary } = ACTION_META[action];
        const size = primary ? 'h-16 w-16' : 'h-[3.25rem] w-[3.25rem] sm:h-14 sm:w-14';
        const iconSize = primary ? 'h-7 w-7' : 'h-6 w-6';
        return (
          <button
            key={action}
            type="button"
            onClick={() => onAction(action)}
            aria-label={cfg.label}
            title={cfg.label}
            className={`group flex ${size} items-center justify-center rounded-full border-2 bg-surface/90 shadow-card backdrop-blur-sm transition-transform duration-150 hover:scale-110 active:scale-90`}
            style={{
              borderColor: cfg.color,
              color: cfg.color,
              boxShadow: `0 8px 24px -10px ${cfg.color}80`,
            }}
          >
            <Icon className={iconSize} />
          </button>
        );
      })}

      <button
        type="button"
        onClick={onToggleDetails}
        className="flex h-11 w-11 items-center justify-center rounded-full border border-white/10 bg-surface/80 text-muted shadow-card transition hover:scale-105 hover:border-warm hover:text-ink active:scale-95"
        aria-label="Toggle details"
        title="Details"
      >
        <InfoIcon className="h-5 w-5" />
      </button>

      <span className="sr-only" aria-live="polite">
        {swiped} swiped
      </span>
    </div>
  );
}
