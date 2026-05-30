"""SQLite/SQLAlchemy session management and the movie catalog ORM model.

The relational store holds the canonical catalog and backs ``GET /search``. It
is seeded at startup from the same ``movie_index.json`` that aligns the ML
matrices, so the SQL view and the ML view never drift. Switching to Postgres is
a one-line ``DATABASE_URL`` change — no code change — because everything goes
through SQLAlchemy 2.0 typed models.

Phase 3 (accounts/history) adds ``users`` and ``sessions`` tables alongside
``movies`` here.
"""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Iterator

from sqlalchemy import JSON, DateTime, Engine, String, create_engine, func, select
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


@lru_cache
def get_engine() -> Engine:
    """Return the cached SQLAlchemy engine built from ``DATABASE_URL``.

    SQLite needs ``check_same_thread=False`` so the connection can be shared
    across FastAPI's threadpool workers.
    """
    url = get_settings().database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, future=True)


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
    """Create all tables if they do not already exist."""
    Base.metadata.create_all(get_engine())


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
