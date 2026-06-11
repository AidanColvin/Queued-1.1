"""SQLite/SQLAlchemy session management and the movie catalog ORM model.

The relational store holds the canonical catalog and backs ``GET /search``. It
is seeded at startup from the same ``movie_index.json`` that aligns the ML
matrices, so the SQL view and the ML view never drift. Switching to Postgres is
a one-line ``DATABASE_URL`` change — no code change — because everything goes
through SQLAlchemy 2.0 typed models.

Phase 3 (accounts/history) adds ``users``, ``user_profiles`` (the persisted
cross-session taste vector), and ``user_saved_titles`` tables alongside
``movies`` here.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Iterator

from sqlalchemy import JSON, DateTime, Engine, NullPool, String, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from config import get_settings
from ml.artifacts import MovieRecord


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class Movie(Base):
    """A catalog title, mirroring one :class:`~ml.artifacts.MovieRecord`."""

    __tablename__ = "movies"

    idx: Mapped[int] = mapped_column(primary_key=True)
    movie_id: Mapped[int] = mapped_column(index=True)
    tmdb_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(512), index=True)
    title_norm: Mapped[str] = mapped_column(String(512), index=True)
    year: Mapped[int | None] = mapped_column(nullable=True)
    type: Mapped[str] = mapped_column(String(8))
    genres: Mapped[list] = mapped_column(JSON, default=list)
    poster_url: Mapped[str | None] = mapped_column(String(512), nullable=True)


class SwipeEvent(Base):
    """One recorded swipe — the source of truth for Layer 3 offline retraining.

    Anonymous by default: ``user_id`` stays null until accounts arrive (Phase 3).
    """

    __tablename__ = "swipe_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    user_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    tmdb_id: Mapped[int] = mapped_column(index=True)
    action: Mapped[str] = mapped_column(String(16))
    time_on_card_ms: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    """A registered account (Phase 3).

    ``hashed_password`` is null for Google-only sign-ups; ``google_sub`` is null
    for email/password-only accounts. An account can carry both once a user who
    registered by email later signs in with the same Google email (the OAuth
    callback links them).
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str | None] = mapped_column(String(128), nullable=True)
    google_sub: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    apple_sub: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # True once the address is proven (verification link, or an OAuth provider
    # that already verified it). Informational for now — nothing is gated on it.
    email_verified: Mapped[bool] = mapped_column(default=False)
    # Flipped after the one-time "pick your streaming services" screen (saving
    # OR skipping), so returning users go straight to the deck.
    onboarding_completed: Mapped[bool] = mapped_column(default=False)
    # Connected Letterboxd account (public RSS / CSV import — no OAuth).
    letterboxd_username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExternalRating(Base):
    """One film imported from an external service (Letterboxd RSS or CSV).

    Kept verbatim (title/year/rating) even when the film doesn't match the
    catalog, so unmatched rows are reviewable and a later catalog expansion can
    re-match them. ``movie_id``/``tmdb_id`` are filled when matched. Logical
    uniqueness on ``(user_id, source, title, year)`` is enforced by upsert in
    the import code, which is what makes re-syncs idempotent.
    """

    __tablename__ = "external_ratings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    source: Mapped[str] = mapped_column(String(16), default="letterboxd")
    title: Mapped[str] = mapped_column(String(512))
    year: Mapped[int | None] = mapped_column(nullable=True)
    rating: Mapped[float | None] = mapped_column(nullable=True)  # 0.5–5.0 stars
    movie_id: Mapped[int | None] = mapped_column(nullable=True, index=True)
    tmdb_id: Mapped[int | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UserProvider(Base):
    """One streaming service a user subscribes to (canonical TMDB id)."""

    __tablename__ = "user_providers"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    provider_id: Mapped[int] = mapped_column(primary_key=True)


class TitleProvider(Base):
    """One (title, service, region) availability fact.

    Mirrored at startup from the ``providers.json`` artifact written by
    ``data.enrich_providers`` — the same seed-from-artifacts pattern as
    ``movies``. Runtime filtering reads the in-memory
    :class:`~providers.ProviderIndex`; this table is the SQL-queryable copy.
    """

    __tablename__ = "title_providers"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    tmdb_id: Mapped[int] = mapped_column(index=True)
    provider_id: Mapped[int] = mapped_column(index=True)
    region: Mapped[str] = mapped_column(String(8), default="US")


class UserProfile(Base):
    """A user's persisted cross-session taste vector (Layer 2).

    One row per user. Rewritten on every swipe, so it lives apart from ``users``
    to keep identity reads cheap. ``taste_vector`` is the reranker's
    ``session_vector`` stored as a plain ``list[float]`` (JSON) — portable across
    SQLite and Postgres with no dtype/bytes handling. The DB row is the source of
    truth; the in-memory :class:`~ml.reranker.SessionStore` is just a per-process
    cache that warm-starts from here.
    """

    __tablename__ = "user_profiles"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    taste_vector: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AnonSessionProfile(Base):
    """An anonymous session's taste vector, persisted across restarts.

    Mirrors :class:`UserProfile` but is keyed by the client-generated
    ``session_id`` instead of an account. The in-memory
    :class:`~ml.reranker.SessionStore` stays the hot path; this row is the
    durable copy that warm-starts the session after a process restart or on a
    different instance, so re-ranking keeps working on multi-instance /
    serverless deployments.
    """

    __tablename__ = "anon_session_profiles"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    taste_vector: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(default=0.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UserSavedTitle(Base):
    """A user's UI-facing saved state — liked, watch-listed, or seen titles.

    Distinct from :class:`SwipeEvent` (the analytics/training log): the frontend
    renders watchlist/liked cards verbatim, so the full ``Recommendation`` is
    stored as ``rec_json`` for ``liked``/``wishlist``. ``seen`` rows store only
    ``movie_id`` (the dedupe key) with ``rec_json`` null. Logical uniqueness on
    ``(user_id, movie_id, kind)`` is enforced by upsert in the route, not a DB
    constraint, to keep the cross-dialect schema simple.
    """

    __tablename__ = "user_saved_titles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    movie_id: Mapped[int] = mapped_column(index=True)
    kind: Mapped[str] = mapped_column(String(8))  # "liked" | "wishlist" | "seen"
    rec_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


@lru_cache
def get_engine() -> Engine:
    """Return the cached SQLAlchemy engine built from ``DATABASE_URL``.

    SQLite needs ``check_same_thread=False`` so the connection can be shared
    across FastAPI's threadpool workers.

    On Postgres (production) the engine uses ``NullPool`` so every request opens
    and closes its own connection. Serverless instances (Vercel) are frozen
    between invocations, which would otherwise leave a pooled connection stale;
    a real connection pool belongs in the database side (pgbouncer / the
    provider's pooled endpoint), not in the frozen function.

    A bare ``postgres://`` / ``postgresql://`` URL (the form Neon, Render, Heroku
    hand out) is normalized to the ``postgresql+psycopg`` driver we actually
    ship — SQLAlchemy's default for those is psycopg2, which isn't installed, so
    without this the engine would fail to import its driver.
    """
    url = get_settings().database_url
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False}, future=True)
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://") :]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://") :]
    return create_engine(url, poolclass=NullPool, pool_pre_ping=True, future=True)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Return the cached session factory bound to the engine."""
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency yielding a request-scoped session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def init_db() -> None:
    """Create all tables if they do not already exist, then heal additive drift.

    ``create_all`` never alters existing tables, and serverless deployments
    (Vercel) have no pre-deploy step to run Alembic — so when a release adds
    columns to a table that already exists in production, every query on that
    model would 500. :func:`_ensure_columns` closes that gap for purely
    additive changes; destructive migrations still belong to Alembic (Render
    runs ``alembic upgrade head`` pre-deploy).
    """
    engine = get_engine()
    Base.metadata.create_all(engine)
    _ensure_columns(engine)


def _ensure_columns(engine: Engine) -> None:
    """Add any model columns missing from existing tables (additive only).

    NOT NULL columns get a type-appropriate DEFAULT so existing rows backfill;
    anything unusual is added as nullable rather than failing. Errors are
    logged, never raised — a startup must not die on a healing step.
    """
    import logging

    from sqlalchemy import inspect

    logger = logging.getLogger("queued")
    try:
        inspector = inspect(engine)
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = column.type.compile(engine.dialect)
                ddl = f'ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}'
                if not column.nullable:
                    default = _backfill_default(column)
                    if default is None:
                        ddl += ""  # no safe backfill — add as nullable instead
                    else:
                        ddl += f" NOT NULL DEFAULT {default}"
                with engine.begin() as conn:
                    conn.exec_driver_sql(ddl)
                logger.info("Schema heal: added %s.%s", table.name, column.name)
    except Exception:  # noqa: BLE001 — best-effort healing only
        logger.exception("Schema healing failed (continuing with current schema)")


def _backfill_default(column) -> str | None:
    """A literal DEFAULT for backfilling a new NOT NULL column, or ``None``."""
    from sqlalchemy import Boolean, Float, Integer
    from sqlalchemy import String as SAString

    if isinstance(column.type, Boolean):
        return "FALSE"
    if isinstance(column.type, (Integer, Float)):
        return "0"
    if isinstance(column.type, SAString):
        return "''"
    return None


def seed_movies(catalog: list[MovieRecord]) -> int:
    """Idempotently populate the ``movies`` table from a catalog.

    If the row count already matches the catalog, seeding is skipped so startup
    stays fast on warm databases.

    Args:
        catalog: Movie records to persist.

    Returns:
        The number of rows in the table after seeding.
    """
    from ml.artifacts import normalize_title

    with get_session_factory()() as session:
        existing = session.scalar(select(Movie.idx).limit(1))
        count = session.query(Movie).count() if existing is not None else 0
        if count == len(catalog):
            return count

        session.query(Movie).delete()
        session.add_all(
            Movie(
                idx=rec.idx,
                movie_id=rec.movie_id,
                tmdb_id=rec.tmdb_id,
                title=rec.title,
                title_norm=normalize_title(rec.title),
                year=rec.year,
                type=rec.type,
                genres=rec.genres,
                poster_url=rec.poster_url,
            )
            for rec in catalog
        )
        session.commit()
        return len(catalog)


def seed_title_providers(index) -> int:
    """Idempotently mirror a :class:`~providers.ProviderIndex` into SQL.

    Skipped when the row count already matches (warm database). Returns the
    number of rows after seeding.
    """
    rows = [
        {"tmdb_id": tmdb_id, "provider_id": pid, "region": index.region}
        for tmdb_id, pids in index.items()
        for pid in sorted(pids)
    ]
    with get_session_factory()() as session:
        count = session.query(TitleProvider).count()
        if count == len(rows):
            return count
        session.query(TitleProvider).delete()
        session.add_all(TitleProvider(**row) for row in rows)
        session.commit()
        return len(rows)
