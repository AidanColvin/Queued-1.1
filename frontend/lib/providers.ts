// Streaming-service metadata + the local persistence for a viewer's selection.
// Mirrors backend/providers.py (canonical TMDB watch-provider ids). The list is
// duplicated client-side so the onboarding grid renders instantly with no
// fetch; GET /providers stays the source of truth for availability status.

import type { ProviderFilter } from './types';

export interface ProviderMeta {
  id: number; // canonical TMDB watch-provider id
  slug: string;
  name: string;
  /** Compact label for on-card chips. */
  short: string;
  color: string;
}

export const PROVIDERS: ProviderMeta[] = [
  { id: 8, slug: 'netflix', name: 'Netflix', short: 'Netflix', color: '#E50914' },
  { id: 15, slug: 'hulu', name: 'Hulu', short: 'Hulu', color: '#1CE783' },
  { id: 1899, slug: 'max', name: 'Max', short: 'Max', color: '#0026FF' },
  { id: 337, slug: 'disney_plus', name: 'Disney+', short: 'Disney+', color: '#113CCF' },
  { id: 9, slug: 'prime_video', name: 'Prime Video', short: 'Prime', color: '#00A8E1' },
  { id: 350, slug: 'apple_tv_plus', name: 'Apple TV+', short: 'ATV+', color: '#555555' },
  { id: 531, slug: 'paramount_plus', name: 'Paramount+', short: 'P+', color: '#0064FF' },
  { id: 386, slug: 'peacock', name: 'Peacock', short: 'Peacock', color: '#05AC3F' },
];

export const PROVIDER_BY_ID = new Map(PROVIDERS.map((p) => [p.id, p]));

const SELECTED_KEY = 'nextwatch:providers';
const FILTER_KEY = 'nextwatch:providerFilter';

/** The locally saved service selection (guests; mirror for signed-in users). */
export function loadSelectedProviders(): number[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(SELECTED_KEY) ?? '[]');
    return Array.isArray(parsed) ? parsed.filter((n): n is number => typeof n === 'number') : [];
  } catch {
    return [];
  }
}

export function saveSelectedProviders(ids: number[]): void {
  try {
    localStorage.setItem(SELECTED_KEY, JSON.stringify(ids));
  } catch {
    /* storage unavailable — non-fatal */
  }
}

export function loadProviderFilter(): ProviderFilter {
  try {
    const v = localStorage.getItem(FILTER_KEY);
    return v === 'only' || v === 'prefer' ? v : 'all';
  } catch {
    return 'all';
  }
}

export function saveProviderFilter(filter: ProviderFilter): void {
  try {
    localStorage.setItem(FILTER_KEY, filter);
  } catch {
    /* storage unavailable — non-fatal */
  }
}

/** Display copy for the three-state deck filter toggle. */
export const FILTER_LABELS: Record<ProviderFilter, string> = {
  all: 'All titles',
  only: 'My services',
  prefer: 'Boost mine',
};

/** The next state when the toggle button is tapped. */
export const NEXT_FILTER: Record<ProviderFilter, ProviderFilter> = {
  all: 'only',
  only: 'prefer',
  prefer: 'all',
};
