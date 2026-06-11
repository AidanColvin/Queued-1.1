// Typed fetch wrappers around the Queued backend.
// Base URL comes from NEXT_PUBLIC_API_URL (see .env.local.example).

import { getAuthToken } from './native';
import type {
  AccountHistory,
  AuthUser,
  LetterboxdStatus,
  LetterboxdSummary,
  MediaType,
  PersonalResponse,
  ProviderPrefs,
  Recommendation,
  RecommendResponse,
  SearchResult,
  SearchType,
  SwipeRequest,
  SwipeResponse,
  TrailerResponse,
  UserProviders,
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
  // Native (Capacitor) sessions ride a stored bearer token; web rides the
  // httpOnly cookie (getAuthToken() is always null in the browser).
  const token = getAuthToken();
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    // Send/receive the auth cookie. Same-origin in production; in local dev the
    // backend's CORS allow_credentials + explicit origin make this work too.
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
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
  // 204 No Content (logout, saved) has no body — don't try to parse JSON.
  if (res.status === 204) return undefined as T;
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

/** Serialize the streaming-service filter for a deck request body. */
function providerBody(prefs?: ProviderPrefs) {
  if (!prefs || prefs.filter === 'all') return {};
  return { provider_filter: prefs.filter, providers: prefs.providers };
}

/** Fetch a fresh recommendation deck for the given seed titles. */
export async function getRecommendations(
  titles: string[],
  count = 20,
  excludeIds: number[] = [],
  prefs?: ProviderPrefs,
): Promise<RecommendResponse> {
  return request<RecommendResponse>('/recommend', {
    method: 'POST',
    body: JSON.stringify({ titles, count, exclude_seen: true, exclude_ids: excludeIds, ...providerBody(prefs) }),
  });
}

/** Fetch the seedless, popularity-ranked cold-start deck. POSTed so the
 *  ever-growing "seen" exclude list never hits URL-length limits. */
export async function getPopular(
  count = 20,
  excludeIds: number[] = [],
  prefs?: ProviderPrefs,
): Promise<RecommendResponse> {
  return request<RecommendResponse>('/popular', {
    method: 'POST',
    body: JSON.stringify({ count, exclude_ids: excludeIds, ...providerBody(prefs) }),
  });
}

/** Fetch the taste-driven movie deck: candidates nearest the visitor's
 *  accumulated taste vector (likes + dislikes + collaborative signal), with a
 *  server-side popularity fallback before there's enough signal. `sessionId`
 *  keys the anonymous taste vector; a signed-in caller is keyed by the cookie. */
export async function getAdaptive(
  sessionId: string,
  count = 20,
  excludeIds: number[] = [],
  prefs?: ProviderPrefs,
): Promise<RecommendResponse> {
  return request<RecommendResponse>('/recommend/adaptive', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, count, exclude_ids: excludeIds, ...providerBody(prefs) }),
  });
}

/** Fetch the popularity-ranked TV deck (separate keyless catalog — no ML model). */
export async function getTv(
  count = 20,
  excludeIds: number[] = [],
  prefs?: ProviderPrefs,
): Promise<RecommendResponse> {
  return request<RecommendResponse>('/tv', {
    method: 'POST',
    body: JSON.stringify({ count, exclude_ids: excludeIds, ...providerBody(prefs) }),
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

// --------------------------------------------------------------------------- #
// Accounts (Phase 3) — email/password + Google, plus per-user saved state.
// All of these ride the httpOnly auth cookie (see `credentials: 'include'`).
// --------------------------------------------------------------------------- #

/** The current signed-in user, or null if the request is anonymous (401). */
export async function getMe(): Promise<AuthUser | null> {
  try {
    return await request<AuthUser>('/auth/me');
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) return null;
    throw err;
  }
}

/** Create an account with email + password; the response sets the session cookie. */
export async function register(email: string, password: string, displayName?: string): Promise<AuthUser> {
  return request<AuthUser>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, display_name: displayName || null }),
  });
}

/** Sign in with email + password. */
export async function login(email: string, password: string): Promise<AuthUser> {
  return request<AuthUser>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  });
}

/** Clear the session cookie. */
export async function logout(): Promise<void> {
  await request<unknown>('/auth/logout', { method: 'POST' });
}

/** The path the browser navigates to for "Continue with Google" (full redirect). */
export function googleLoginUrl(): string {
  return `${API_URL}/auth/google/login`;
}

/** Exchange a native Sign-in-with-Apple identity token for a session. */
export async function appleSignIn(identityToken: string, displayName?: string | null): Promise<AuthUser> {
  return request<AuthUser>('/auth/apple', {
    method: 'POST',
    body: JSON.stringify({ identity_token: identityToken, display_name: displayName ?? null }),
  });
}

/** Ask for a password-reset email. Always resolves (the backend never reveals
 *  whether the address has an account). */
export async function requestPasswordReset(email: string): Promise<void> {
  await request<unknown>('/auth/request-password-reset', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

/** Complete a password reset with the emailed token. */
export async function resetPassword(token: string, newPassword: string): Promise<void> {
  await request<unknown>('/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify({ token, new_password: newPassword }),
  });
}

/** Confirm an email address with the emailed verification token. */
export async function verifyEmail(token: string): Promise<void> {
  await request<unknown>('/auth/verify-email', { method: 'POST', body: JSON.stringify({ token }) });
}

/** Permanently delete the signed-in account and all of its data. */
export async function deleteAccount(): Promise<void> {
  await request<unknown>('/account', { method: 'DELETE' });
}

/** The signed-in user's saved streaming services. */
export async function getMyProviders(): Promise<UserProviders> {
  return request<UserProviders>('/account/providers');
}

/** Replace the signed-in user's streaming services (also completes onboarding). */
export async function setMyProviders(providers: number[], complete = true): Promise<UserProviders> {
  return request<UserProviders>('/account/providers', {
    method: 'PUT',
    body: JSON.stringify({ providers, complete }),
  });
}

/** The "For You" shelves. Signed-in users are recognized by their cookie; for
 *  guests the session's liked titles ride along as seeds. */
export async function getPersonal(seeds: string[] = [], prefs?: ProviderPrefs): Promise<PersonalResponse> {
  const params = new URLSearchParams();
  if (seeds.length) params.set('seeds', seeds.slice(0, 12).join(','));
  if (prefs && prefs.filter !== 'all') {
    params.set('provider_filter', prefs.filter);
    if (prefs.providers.length) params.set('providers', prefs.providers.join(','));
  }
  const qs = params.toString();
  return request<PersonalResponse>(`/recommendations/personal${qs ? `?${qs}` : ''}`);
}

// --------------------------------------------------------------------------- #
// Letterboxd (RSS sync + export upload)
// --------------------------------------------------------------------------- #

/** Connection state + import counts for the settings UI. */
export async function getLetterboxdStatus(): Promise<LetterboxdStatus> {
  return request<LetterboxdStatus>('/account/letterboxd');
}

/** Import the user's recent diary from their public Letterboxd RSS feed. */
export async function syncLetterboxd(username: string): Promise<LetterboxdSummary> {
  return request<LetterboxdSummary>('/account/letterboxd/sync', {
    method: 'POST',
    body: JSON.stringify({ username }),
  });
}

/** Upload a Letterboxd data export (ZIP, ratings.csv, or watched.csv). */
export async function importLetterboxd(file: File): Promise<LetterboxdSummary> {
  const form = new FormData();
  form.append('file', file);
  const token = getAuthToken();
  // Multipart: let the browser set the boundary Content-Type itself.
  const res = await fetch(`${API_URL}/account/letterboxd/import`, {
    method: 'POST',
    credentials: 'include',
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = ((await res.json()) as { detail?: string }).detail ?? detail;
    } catch {
      /* no JSON body */
    }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<LetterboxdSummary>;
}

/** Load the signed-in user's saved deck state (liked/wishlist recs + seen ids). */
export async function getHistory(): Promise<AccountHistory> {
  return request<AccountHistory>('/account/history');
}

/** Merge a guest's local deck state into the account; returns the merged state. */
export async function mergeGuestData(data: AccountHistory): Promise<AccountHistory> {
  return request<AccountHistory>('/account/merge', { method: 'POST', body: JSON.stringify(data) });
}

/** Persist one liked/watch-listed card to the account (fire-and-forget). */
export async function saveTitle(rec: Recommendation, kind: 'liked' | 'wishlist'): Promise<void> {
  await request<unknown>('/account/saved', { method: 'POST', body: JSON.stringify({ rec, kind }) });
}

/** Resolve a title's YouTube trailer key so it can play in an in-page player.
 *  `title`/`year` power the backend's keyless YouTube-search fallback, so a
 *  trailer resolves even without a TMDB key (or a TMDB id). */
export async function getTrailer(
  tmdbId: number | null,
  type: MediaType,
  title?: string,
  year?: number | null,
): Promise<TrailerResponse> {
  const params = new URLSearchParams({ type });
  if (title) params.set('title', title);
  if (year != null) params.set('year', String(year));
  return request<TrailerResponse>(`/trailer/${tmdbId ?? 0}?${params}`);
}

export interface TasteMatch {
  user_a: string;
  user_b: string;
  cosine_similarity: number;
  match_percentage: number;
}

/** Compare two taste profiles (anon session ids or numeric user ids) → cosine
 *  similarity + a 0–100% match rate. Routed through the shared `request` helper
 *  so it uses the `/api` origin and auth like every other call (the standalone
 *  fetch it replaced fell back to http://localhost:8000 in production). */
export async function getTasteMatch(userA: string, userB: string): Promise<TasteMatch> {
  const params = new URLSearchParams({ user_a: userA, user_b: userB });
  return request<TasteMatch>(`/social/match?${params}`);
}
