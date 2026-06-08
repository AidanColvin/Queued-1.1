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
  liked: { label: 'LIKE', color: '#3ecf8e', exit: { x: 640, y: 0, rotate: 26 }, arrow: '→' },
  dismissed: { label: 'DISLIKE', color: '#ff5e5b', exit: { x: -640, y: 0, rotate: -26 }, arrow: '←' },
  saved: { label: 'SAVE', color: '#4aa8ff', exit: { x: 0, y: -760, rotate: 0 }, arrow: '↑' },
  skip: { label: 'NOT SEEN', color: '#8a9099', exit: { x: 0, y: 760, rotate: 0 }, arrow: '↓' },
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
