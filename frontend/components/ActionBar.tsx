'use client';

import { ACTION_BAR_ORDER, ACTION_CONFIG } from '@/lib/actions';
import type { SwipeAction } from '@/lib/types';

interface ActionBarProps {
  swiped: number;
  canUndo: boolean;
  onAction: (action: SwipeAction) => void;
  onUndo: () => void;
  onToggleDetails: () => void;
}

export default function ActionBar({
  swiped,
  canUndo,
  onAction,
  onUndo,
  onToggleDetails,
}: ActionBarProps) {
  return (
    <div className="flex items-center justify-between gap-2 px-1 sm:gap-3">
      <button
        type="button"
        onClick={onUndo}
        disabled={!canUndo}
        className="flex h-12 min-w-12 items-center justify-center rounded-full border border-white/10 px-3 text-sm text-ink transition enabled:hover:border-warm disabled:opacity-30"
        aria-label="Undo last swipe"
      >
        ↶<span className="ml-1 hidden sm:inline">Undo</span>
      </button>

      <div className="flex items-center gap-1.5 sm:gap-2">
        {ACTION_BAR_ORDER.map((action) => {
          const cfg = ACTION_CONFIG[action];
          return (
            <button
              key={action}
              type="button"
              onClick={() => onAction(action)}
              aria-label={cfg.label}
              title={cfg.label}
              className="flex h-11 w-11 items-center justify-center rounded-full border bg-surface text-xl transition hover:scale-105 active:scale-95 sm:h-12 sm:w-12"
              style={{ borderColor: cfg.color, color: cfg.color }}
            >
              {cfg.arrow}
            </button>
          );
        })}
      </div>

      <div className="flex items-center gap-2">
        <span className="hidden tabular-nums text-sm text-muted sm:inline" aria-label="Swiped count">
          {swiped} swiped
        </span>
        <button
          type="button"
          onClick={onToggleDetails}
          className="flex h-12 w-12 items-center justify-center rounded-full border border-white/10 text-ink transition hover:border-warm"
          aria-label="Toggle details"
        >
          ⋯
        </button>
      </div>
    </div>
  );
}
