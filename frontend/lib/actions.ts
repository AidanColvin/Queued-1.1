// Mapping from the four swipe actions to their visual identity, exit vector,
// and keyboard bindings. Shared by the card, action bar and key hints.

import type { SwipeAction } from './types';

export interface ActionConfig {
  label: string;
  color: string;
  /** Exit target for the fly-off animation. */
  exit: { x: number; y: number; rotate: number };
  /** Bottom-bar arrow glyph. */
  arrow: string;
}

export const ACTION_CONFIG: Record<SwipeAction, ActionConfig> = {
  liked: { label: 'LIKE', color: '#34c759', exit: { x: 640, y: 0, rotate: 26 }, arrow: '→' },
  dismissed: { label: 'DISLIKE', color: '#ff3b30', exit: { x: -640, y: 0, rotate: -26 }, arrow: '←' },
  saved: { label: 'SAVE', color: '#0a84ff', exit: { x: 0, y: -760, rotate: 0 }, arrow: '↑' },
  skip: { label: 'NOT SEEN', color: '#8e8e93', exit: { x: 0, y: 760, rotate: 0 }, arrow: '↓' },
  // Double-tap the centre of a card. Not a swipe direction and not on the
  // action bar — it flies straight up like SAVE but reads as a stronger LIKE
  // (gold ★), and the backend weights it well above an ordinary like.
  superliked: { label: 'SUPER LIKE', color: '#ffd60a', exit: { x: 0, y: -820, rotate: 0 }, arrow: '★' },
};

/** Keyboard bindings → action (WASD + arrows). Lowercased keys / arrow names. */
export const KEY_TO_ACTION: Record<string, SwipeAction> = {
  d: 'liked',
  arrowright: 'liked',
  a: 'dismissed',
  arrowleft: 'dismissed',
  w: 'saved',
  arrowup: 'saved',
  s: 'skip',
  arrowdown: 'skip',
};

/** Order used for the bottom action bar (PASS, SAVE, SKIP, LIKE). */
export const ACTION_BAR_ORDER: SwipeAction[] = ['dismissed', 'saved', 'skip', 'liked'];
