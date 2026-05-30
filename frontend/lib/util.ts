// Small shared helpers.

/** Generate an opaque, anonymous session id for swipe tracking. */
export function makeSessionId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `s-${Date.now().toString(36)}-${Math.floor(Math.random() * 1e9).toString(36)}`;
}

/** Encode seed titles into a shareable, bookmarkable query string. */
export function encodeTitles(titles: string[]): string {
  return new URLSearchParams({ titles: JSON.stringify(titles) }).toString();
}

/** Parse seed titles back out of a URLSearchParams. Tolerant of bad input. */
export function decodeTitles(params: URLSearchParams | null): string[] {
  const raw = params?.get('titles');
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.filter((t): t is string => typeof t === 'string');
    }
  } catch {
    /* fall through */
  }
  return [];
}

/** A stable key for a set of seed titles (order-independent). */
export function titlesKey(titles: string[]): string {
  return [...titles].map((t) => t.toLowerCase().trim()).sort().join('|');
}

/** TMDB page URL for a title (where users can find where to watch). */
export function tmdbUrl(tmdbId: number | null, type: 'movie' | 'tv'): string {
  if (tmdbId == null) return '#';
  return `https://www.themoviedb.org/${type === 'tv' ? 'tv' : 'movie'}/${tmdbId}`;
}

/** YouTube search that lands on the title's trailer (keyless, always works). */
export function youtubeTrailerUrl(title: string, year: number | null): string {
  const q = `${title} ${year ?? ''} trailer`.trim();
  return `https://www.youtube.com/results?search_query=${encodeURIComponent(q)}`;
}
