'use client';

// Keyless poster backfill. The bundled catalog gets its posters from Wikipedia,
// which misses some titles — notably a chunk of popular TV shows (The Sopranos,
// Black Mirror, …). For those we resolve a real poster at runtime from TVmaze
// (free, no API key, CORS-enabled, returns portrait artwork). Results are cached
// in memory + localStorage so each show is looked up at most once.

import { useEffect, useState } from 'react';

import type { Recommendation } from './types';

const memCache = new Map<string, string | null>();
const LS_PREFIX = 'nextwatch:poster:';

function cacheKey(title: string): string {
  return title.trim().toLowerCase();
}

async function fetchTvmazePoster(title: string): Promise<string | null> {
  try {
    const res = await fetch(`https://api.tvmaze.com/singlesearch/shows?q=${encodeURIComponent(title)}`);
    if (!res.ok) return null;
    const data = (await res.json()) as { image?: { original?: string; medium?: string } };
    return data?.image?.original ?? data?.image?.medium ?? null;
  } catch {
    return null;
  }
}

/**
 * Best poster URL for a card. Returns the real (Wikipedia) poster immediately
 * when present; otherwise, for TV titles, resolves one keylessly from TVmaze.
 * Movies without a poster (rare) resolve to null → the card shows its tile.
 */
export async function resolvePoster(rec: Recommendation): Promise<string | null> {
  if (rec.poster_url) return rec.poster_url;
  if (rec.type !== 'tv') return null;

  const key = cacheKey(rec.title);
  if (memCache.has(key)) return memCache.get(key) ?? null;

  // localStorage stores '' for "looked up, none found" to avoid re-querying.
  try {
    const cached = localStorage.getItem(LS_PREFIX + key);
    if (cached !== null) {
      const val = cached || null;
      memCache.set(key, val);
      return val;
    }
  } catch {
    /* localStorage unavailable — fall through to network */
  }

  const url = await fetchTvmazePoster(rec.title);
  memCache.set(key, url);
  try {
    localStorage.setItem(LS_PREFIX + key, url ?? '');
  } catch {
    /* ignore quota/availability errors */
  }
  return url;
}

/**
 * React hook returning the best available poster URL for a card, or null while
 * a keyless lookup is in flight / if none exists. Re-resolves when the card
 * changes.
 */
export function useCardPoster(rec: Recommendation): string | null {
  const [url, setUrl] = useState<string | null>(rec.poster_url ?? null);

  useEffect(() => {
    if (rec.poster_url) {
      setUrl(rec.poster_url);
      return;
    }
    let alive = true;
    setUrl(null);
    void resolvePoster(rec).then((resolved) => {
      if (alive) setUrl(resolved);
    });
    return () => {
      alive = false;
    };
    // rec.id keys the card; poster_url is the only field that flips resolution.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rec.id, rec.poster_url]);

  return url;
}
