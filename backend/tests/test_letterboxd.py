"""Phase 3: Letterboxd RSS sync + CSV/ZIP import."""

from __future__ import annotations

import io
import zipfile

import pytest


def _register(api, email: str) -> dict:
    res = api.post("/auth/register", json={"email": email, "password": "hunter2secret"})
    assert res.status_code == 200, res.text
    return res.json()


@pytest.fixture
def catalog_films(client) -> list[dict]:
    """A few real catalog titles (title/year/tmdb_id) to build feeds around."""
    recs = client.post("/popular", json={"count": 6}).json()["recommendations"]
    films = [r for r in recs if r["year"] and r["tmdb_id"]]
    assert len(films) >= 3
    return films[:3]


def _rss(films: list[tuple[dict, float | None]]) -> str:
    items = "".join(
        f"""
        <item>
          <title>{f['title']}, {f['year']}</title>
          <letterboxd:filmTitle>{f['title']}</letterboxd:filmTitle>
          <letterboxd:filmYear>{f['year']}</letterboxd:filmYear>
          {f'<letterboxd:memberRating>{rating}</letterboxd:memberRating>' if rating is not None else ''}
          <tmdb:movieId>{f['tmdb_id']}</tmdb:movieId>
        </item>"""
        for f, rating in films
    )
    return (
        '<?xml version="1.0"?><rss xmlns:letterboxd="https://letterboxd.com" '
        'xmlns:tmdb="https://themoviedb.org"><channel>' + items + "</channel></rss>"
    )


def test_rss_sync_imports_likes_and_seen(api, catalog_films, monkeypatch):
    from routers import letterboxd as lb_router

    loved, mid, watched = catalog_films
    feed = _rss([(loved, 5.0), (mid, 2.5), (watched, None)])
    monkeypatch.setattr(lb_router, "fetch_rss", lambda username: feed)

    _register(api, "lb@example.com")
    res = api.post("/account/letterboxd/sync", json={"username": "Cinephile_99"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 3
    assert body["matched"] == 3
    assert body["liked"] == 1  # only the 5.0★
    assert body["seen"] == 3  # every matched film leaves the deck
    assert body["unmatched"] == []

    # The like landed in history with its Letterboxd provenance.
    hist = api.get("/account/history").json()
    liked_titles = [r["title"] for r in hist["liked"]]
    assert loved["title"] in liked_titles
    assert {loved["id"], mid["id"], watched["id"]} <= set(hist["seen"])

    # Username saved; counts reported.
    status = api.get("/account/letterboxd").json()
    assert status["username"] == "cinephile_99"
    assert status["imported"] == 3 and status["matched"] == 3

    # Re-sync is idempotent: nothing new is added.
    again = api.post("/account/letterboxd/sync", json={"username": "cinephile_99"}).json()
    assert again["liked"] == 0 and again["seen"] == 0


def test_rss_sync_reports_unmatched(api, monkeypatch):
    from routers import letterboxd as lb_router

    fake = {"title": "A Film That Does Not Exist Anywhere", "year": 1937, "tmdb_id": 99999999}
    monkeypatch.setattr(lb_router, "fetch_rss", lambda username: _rss([(fake, 4.0)]))

    _register(api, "lb-unmatched@example.com")
    body = api.post("/account/letterboxd/sync", json={"username": "someone"}).json()
    assert body["total"] == 1 and body["matched"] == 0
    assert "A Film That Does Not Exist Anywhere (1937)" in body["unmatched"]


def test_sync_rejects_bad_username_and_requires_auth(api):
    assert api.post("/account/letterboxd/sync", json={"username": "ok_name"}).status_code == 401
    _register(api, "lb-bad@example.com")
    res = api.post("/account/letterboxd/sync", json={"username": "no/slashes"})
    assert res.status_code == 422


def _ratings_csv(rows: list[tuple[str, int, float]]) -> bytes:
    lines = ["Date,Name,Year,Letterboxd URI,Rating"]
    lines += [f"2024-01-01,{title},{year},https://boxd.it/x,{rating}" for title, year, rating in rows]
    return "\n".join(lines).encode()


def test_csv_upload_import(api, catalog_films):
    loved = catalog_films[0]
    _register(api, "lb-csv@example.com")
    csv_bytes = _ratings_csv([(loved["title"], loved["year"], 4.5), ("Totally Unknown Film", 1931, 5.0)])

    res = api.post(
        "/account/letterboxd/import",
        files={"file": ("ratings.csv", csv_bytes, "text/csv")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 2 and body["matched"] == 1 and body["liked"] == 1
    assert any("Totally Unknown Film" in t for t in body["unmatched"])


def test_zip_upload_import(api, catalog_films):
    loved, _, watched = catalog_films
    _register(api, "lb-zip@example.com")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("ratings.csv", _ratings_csv([(loved["title"], loved["year"], 4.0)]))
        z.writestr(
            "watched.csv",
            f"Date,Name,Year,Letterboxd URI\n2024-01-01,{watched['title']},{watched['year']},https://boxd.it/y\n",
        )

    res = api.post(
        "/account/letterboxd/import",
        files={"file": ("letterboxd-export.zip", buf.getvalue(), "application/zip")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 2 and body["matched"] == 2
    assert body["liked"] == 1 and body["seen"] == 2


def test_import_rejects_unreadable_file(api):
    _register(api, "lb-junk@example.com")
    res = api.post("/account/letterboxd/import", files={"file": ("noise.csv", b"\x00\x01\x02", "text/csv")})
    assert res.status_code == 422
