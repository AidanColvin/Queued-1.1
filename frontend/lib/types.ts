// Shared types mirroring the backend Pydantic schemas (backend/schemas.py).

export type MediaType = 'movie' | 'tv';
export type SearchType = 'movie' | 'tv' | 'all';

/** The four swipe directions, plus the double-tap "super like". */
export type SwipeAction = 'liked' | 'saved' | 'dismissed' | 'skip' | 'superliked';

/** Deck filtering by streaming service: everything, hard filter, or soft boost. */
export type ProviderFilter = 'all' | 'only' | 'prefer';

/** What the deck endpoints need to apply the streaming-service filter. */
export interface ProviderPrefs {
  filter: ProviderFilter;
  providers: number[];
}

export interface SearchResult {
  tmdb_id: number | null;
  title: string;
  year: number | null;
  type: MediaType;
  poster_url: string | null;
}

export interface Recommendation {
  id: number; // stable unique id (movie_id) — dedupe/exclude key
  title: string;
  year: number | null;
  type: MediaType;
  score: number;
  genres: string[];
  cast: string[];
  overview: string;
  poster_url: string | null;
  tmdb_id: number | null;
  /** YouTube video id baked in keylessly — lets the trailer play in-page. */
  trailer_key: string | null;
  /** Canonical streaming-provider ids carrying this title (may be empty). */
  providers?: number[];
  why: string;
}

export interface TasteProfile {
  top_genres: string[];
  mood_tags: string[];
  era_bias: string;
}

export interface RecommendResponse {
  recommendations: Recommendation[];
  taste_profile: TasteProfile;
}

export interface SwipeRequest {
  session_id: string;
  tmdb_id: number;
  action: SwipeAction;
  time_on_card_ms: number;
  remaining: number[];
  provider_filter?: ProviderFilter;
  providers?: number[];
}

export interface SwipeResponse {
  reranked_queue: number[];
  session_confidence: number;
  applied: boolean;
}

export interface TrailerResponse {
  youtube_key: string | null;
  name: string | null;
  source: 'tmdb' | 'none' | 'unconfigured' | 'error';
}

/** A user's decision on a single card — the unit persisted for undo + history. */
export interface CardDecision {
  tmdbId: number;
  title: string;
  action: SwipeAction;
  timestamp: number;
}

/** Public view of a signed-in account (mirrors backend ``UserOut``). */
export interface AuthUser {
  id: number;
  email: string;
  display_name: string | null;
  email_verified: boolean;
  /** True once the one-time streaming-services screen was saved or skipped. */
  onboarding_completed: boolean;
  /** Present on login/register responses only — the session JWT the native
   *  (Capacitor) shell stores and replays as a Bearer header. */
  access_token?: string | null;
}

/** A user's saved streaming services (mirrors backend ``UserProvidersResponse``). */
export interface UserProviders {
  providers: number[];
  onboarding_completed: boolean;
}

/** One ranked shelf on the For You page (mirrors backend ``PersonalSection``). */
export interface PersonalSection {
  key: string;
  title: string;
  items: Recommendation[];
}

/** Response of GET /recommendations/personal. */
export interface PersonalResponse {
  sections: PersonalSection[];
  seeded_by: string[];
  signed_in: boolean;
}

/** Outcome of a Letterboxd import (mirrors backend ``LetterboxdSummary``). */
export interface LetterboxdSummary {
  total: number;
  matched: number;
  liked: number;
  seen: number;
  unmatched: string[];
}

/** Letterboxd connection state (mirrors backend ``LetterboxdStatus``). */
export interface LetterboxdStatus {
  username: string | null;
  imported: number;
  matched: number;
}

/** A user's server-persisted deck state (mirrors backend ``HistoryResponse``). */
export interface AccountHistory {
  liked: Recommendation[];
  wishlist: Recommendation[];
  seen: number[];
}
