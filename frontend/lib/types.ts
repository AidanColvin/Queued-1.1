// Shared types mirroring the backend Pydantic schemas (backend/schemas.py).

export type MediaType = 'movie' | 'tv';
export type SearchType = 'movie' | 'tv' | 'all';

/** The four swipe directions. */
export type SwipeAction = 'liked' | 'saved' | 'dismissed' | 'skip';

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
}

export interface SwipeResponse {
  reranked_queue: number[];
  session_confidence: number;
  applied: boolean;
}

/** A user's decision on a single card — the unit persisted for undo + history. */
export interface CardDecision {
  tmdbId: number;
  title: string;
  action: SwipeAction;
  timestamp: number;
}
