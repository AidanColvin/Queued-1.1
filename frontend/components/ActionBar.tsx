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
        className="flex h-11 w-11 items-center justify-center rounded-full text-lg text-muted transition enabled:hover:bg-surface-2 enabled:active:scale-95 disabled:opacity-25"
        aria-label="Undo last swipe"
        title="Undo"
      >
        ↶
      </button>

      <div className="flex items-center gap-2.5 sm:gap-3">
        {ACTION_BAR_ORDER.map((action) => {
          const cfg = ACTION_CONFIG[action];
          return (
            <button
              key={action}
              type="button"
              onClick={() => onAction(action)}
              aria-label={cfg.label}
              title={cfg.label}
              className="flex h-12 w-12 items-center justify-center rounded-full bg-white text-xl font-semibold ring-1 ring-black/[0.06] shadow-soft transition hover:scale-110 hover:ring-black/10 active:scale-95 sm:h-[52px] sm:w-[52px]"
              style={{ color: cfg.color }}
            >
              {cfg.arrow}
            </button>
          );
        })}
      </div>

      <button
        type="button"
        onClick={onToggleDetails}
        className="flex h-11 w-11 items-center justify-center rounded-full text-lg text-muted transition hover:bg-surface-2 active:scale-95"
        aria-label="Toggle details"
        title="Details"
      >
        ⓘ
      </button>
    </div>
  );
}
