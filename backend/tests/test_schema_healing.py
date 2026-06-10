"""The serverless schema-healing step in ``init_db``.

Reproduces the production incident: a ``users`` table created by an older
release (no ``apple_sub`` / ``email_verified`` / ``onboarding_completed`` /
``letterboxd_username``) made every signed-in request 500 on Vercel, where
nothing runs Alembic. ``init_db`` must add the missing columns in place.
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text


def test_init_db_adds_missing_columns_to_existing_table(tmp_path, monkeypatch, client):
    import db.database as database

    url = f"sqlite:///{tmp_path / 'old_schema.db'}"
    old = create_engine(url, future=True)
    with old.begin() as conn:
        # The users table exactly as the pre-Phase-1 release created it.
        conn.execute(
            text(
                """
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email VARCHAR(320) NOT NULL,
                    hashed_password VARCHAR(128),
                    google_sub VARCHAR(64),
                    display_name VARCHAR(128),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        conn.execute(text("INSERT INTO users (email) VALUES ('legacy@example.com')"))

    # Point the app's engine at the legacy database and run startup DDL.
    monkeypatch.setenv("DATABASE_URL", url)
    from config import get_settings

    get_settings.cache_clear()
    database.get_engine.cache_clear()
    database.get_session_factory.cache_clear()
    try:
        database.init_db()

        cols = {c["name"] for c in inspect(database.get_engine()).get_columns("users")}
        assert {"apple_sub", "email_verified", "onboarding_completed", "letterboxd_username"} <= cols

        # The legacy row is intact, queryable through the NEW model, and the
        # NOT NULL booleans were backfilled to false.
        with database.get_session_factory()() as session:
            user = session.query(database.User).filter_by(email="legacy@example.com").one()
            assert user.email_verified is False
            assert user.onboarding_completed is False
            assert user.apple_sub is None

        # Healing is idempotent — a second startup is a no-op, not an error.
        database.init_db()
    finally:
        # monkeypatch restores DATABASE_URL after this; clearing the caches here
        # makes the next consumer rebuild from the restored env.
        get_settings.cache_clear()
        database.get_engine.cache_clear()
        database.get_session_factory.cache_clear()
