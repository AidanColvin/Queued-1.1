// Typed fetch wrappers around the NextWatch backend.
// Base URL comes from NEXT_PUBLIC_API_URL (see .env.local.example).

import type {
  MediaType,
  RecommendResponse,
  SearchResult,
  SearchType,
  SwipeRequest,
  SwipeResponse,
  TrailerResponse,
} from './types';

// Backend base URL. In production the backend runs as a Vercel function on the
// same origin under /api, so the default is relative — no env var needed. For
// local dev set NEXT_PUBLIC_API_URL=http://localhost:8000 (see .env.local.example).
const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? '/api').replace(/\/$/, '');

/** Thrown when the backend returns a non-2xx status. */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = (body as { detail?: string }).detail ?? detail;
    } catch {
      /* response had no JSON body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

/** Autocomplete titles. Returns [] for blank queries without hitting the API. */
export async function searchTitles(
  q: string,
  type: SearchType = 'all',
  signal?: AbortSignal,
): Promise<SearchResult[]> {
  const query = q.trim();
  if (!query) return [];
  const params = new URLSearchParams({ q: query, type });
  const data = await request<{ results: SearchResult[] }>(`/search?${params}`, { signal });
  return data.results;
}

/** Fetch a fresh recommendation deck for the given seed titles. */
export async function getRecommendations(
  titles: string[],
  count = 20,
  excludeIds: number[] = [],
): Promise<RecommendResponse> {
  return request<RecommendResponse>('/recommend', {
    method: 'POST',
    body: JSON.stringify({ titles, count, exclude_seen: true, exclude_ids: excludeIds }),
  });
}

/** Fetch the seedless, popularity-ranked cold-start deck. POSTed so the
 *  ever-growing "seen" exclude list never hits URL-length limits. */
export async function getPopular(count = 20, excludeIds: number[] = []): Promise<RecommendResponse> {
  return request<RecommendResponse>('/popular', {
    method: 'POST',
    body: JSON.stringify({ count, exclude_ids: excludeIds }),
  });
}

/** Fetch the popularity-ranked TV deck (separate keyless catalog — no ML model). */
export async function getTv(count = 20, excludeIds: number[] = []): Promise<RecommendResponse> {
  return request<RecommendResponse>('/tv', {
    method: 'POST',
    body: JSON.stringify({ count, exclude_ids: excludeIds }),
  });
}

/**
 * Record a swipe and get the re-ranked remaining deck. Fire-and-forget from the
 * UI's perspective — callers should not block the next card on this.
 */
export async function recordSwipe(req: SwipeRequest): Promise<SwipeResponse> {
  return request<SwipeResponse>('/swipe', {
    method: 'POST',
    body: JSON.stringify(req),
  });
}

/** Resolve a title's YouTube trailer key so it can play in an in-page player. */
export async function getTrailer(tmdbId: number, type: MediaType): Promise<TrailerResponse> {
  const params = new URLSearchParams({ type });
  return request<TrailerResponse>(`/trailer/${tmdbId}?${params}`);
}
