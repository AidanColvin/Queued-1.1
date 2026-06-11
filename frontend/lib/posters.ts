'use client';

// Keyless poster resolution. For TV we prefer TVmaze (free, no API key,
// CORS-enabled, real portrait artwork) over the bundled catalog's Wikipedia
// image — Wikipedia's TV "posters" are frequently just a show logo or a low-res
// upscale (e.g. Game of Thrones, The Big Bang Theory), which look unpolished
// next to the movie posters. Movies keep their Wikipedia poster (those are real
// posters). TVmaze lookups are cached in memory + localStorage (one per show).

import { useEffect, useState } from 'react';

import type { Recommendation } from './types';

const memCache = new Map<string, string | null>();
const LS_PREFIX = 'queued:poster:';

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

/** Cached TVmaze poster lookup by title ('' in localStorage = "looked up, none"). */
async function tvmazePoster(title: string): Promise<string | null> {
  const key = cacheKey(title);
  if (memCache.has(key)) return memCache.get(key) ?? null;
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
  const url = await fetchTvmazePoster(title);
  memCache.set(key, url);
  try {
    localStorage.setItem(LS_PREFIX + key, url ?? '');
  } catch {
    /* ignore quota/availability errors */
  }
  return url;
}

/**
 * Best poster URL for a card. Movies use their (real) Wikipedia poster. TV
 * prefers a proper portrait poster from TVmaze, falling back to the catalog's
 * Wikipedia image only when TVmaze has nothing. Returns null when no artwork
 * exists at all → the card is filtered out upstream.
 */
export async function resolvePoster(rec: Recommendation): Promise<string | null> {
  if (rec.type !== 'tv') return rec.poster_url ?? null;
  const tvmaze = await tvmazePoster(rec.title);
  return tvmaze ?? rec.poster_url ?? null;
}

/**
 * React hook returning the best available poster URL for a card, or null while
 * a keyless lookup is in flight / if none exists. Re-resolves when the card
 * changes.
 */
export function useCardPoster(rec: Recommendation): string | null {
  const [url, setUrl] = useState<string | null>(rec.poster_url ?? null);

  useEffect(() => {
    // Movies: the catalog poster is final. TV: start from whatever we have, then
    // upgrade to the TVmaze portrait (preferred) once it resolves.
    if (rec.type !== 'tv') {
      setUrl(rec.poster_url ?? null);
      return;
    }
    setUrl(rec.poster_url ?? null);
    let alive = true;
    void resolvePoster(rec).then((resolved) => {
      if (alive && resolved) setUrl(resolved);
    });
    return () => {
      alive = false;
    };
    // rec.id keys the card; poster_url is the only field that flips resolution.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rec.id, rec.type, rec.poster_url]);

  return url;
}
