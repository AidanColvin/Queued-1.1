from __future__ import annotations

def test_ratings_columns(ratings_df):
    expected = {"userId", "movieId", "rating"}
    assert expected.issubset(set(ratings_df.columns))

def test_movies_columns(movies_df):
    expected = {"movieId", "title"}
    assert expected.issubset(set(movies_df.columns))

def test_ratings_not_empty(ratings_df):
    assert len(ratings_df) > 100

def test_movies_not_empty(movies_df):
    assert len(movies_df) > 100

def test_ratings_range_valid(ratings_df):
    assert ratings_df["rating"].min() >= 0.5
    assert ratings_df["rating"].max() <= 5.0

def test_user_ids_exist(ratings_df):
    assert ratings_df["userId"].nunique() > 10

def test_movie_ids_exist(ratings_df):
    assert ratings_df["movieId"].nunique() > 100

def test_movies_joinable(ratings_df, movies_df):
    overlap = set(ratings_df["movieId"]).intersection(set(movies_df["movieId"]))
    assert len(overlap) > 100

def test_no_null_movie_titles(movies_df):
    assert movies_df["title"].notna().all()

def test_some_multi_genre_movies(movies_df):
    if "genres" in movies_df.columns:
        assert movies_df["genres"].astype(str).str.contains("|", regex=False).sum() >= 1
