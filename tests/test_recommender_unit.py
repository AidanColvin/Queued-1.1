from __future__ import annotations
import pytest

def test_load_model():
    from backend.app.ml.recommender import load_model
    model = load_model()
    assert model is not None

def test_load_movies():
    from backend.app.ml.recommender import load_movies
    movies = load_movies()
    assert len(movies) > 100

def test_load_ratings():
    from backend.app.ml.recommender import load_ratings
    ratings = load_ratings()
    assert len(ratings) > 100

@pytest.mark.parametrize("user_id,top_n", [(1, 5), (1, 10), (2, 5), (10, 3)])
def test_recommend_for_user_returns_list(user_id, top_n):
    from backend.app.ml.recommender import recommend_for_user
    recs = recommend_for_user(user_id=user_id, top_n=top_n)
    assert isinstance(recs, list)

@pytest.mark.parametrize("user_id,top_n", [(1, 5), (2, 10), (20, 7)])
def test_recommend_for_user_length_cap(user_id, top_n):
    from backend.app.ml.recommender import recommend_for_user
    recs = recommend_for_user(user_id=user_id, top_n=top_n)
    assert len(recs) <= top_n

def test_recommendation_fields():
    from backend.app.ml.recommender import recommend_for_user
    recs = recommend_for_user(user_id=1, top_n=5)
    if recs:
        first = recs[0]
        assert "movieId" in first
        assert "title" in first
        assert "predicted_rating" in first

def test_recommendation_scores_sorted_desc():
    from backend.app.ml.recommender import recommend_for_user
    recs = recommend_for_user(user_id=1, top_n=10)
    scores = [r["predicted_rating"] for r in recs]
    assert scores == sorted(scores, reverse=True)

def test_recommendations_exclude_seen_movies():
    from backend.app.ml.recommender import recommend_for_user, load_ratings
    ratings = load_ratings()
    seen = set(ratings.loc[ratings["userId"] == 1, "movieId"].tolist())
    recs = recommend_for_user(user_id=1, top_n=10)
    returned = {r["movieId"] for r in recs}
    assert seen.isdisjoint(returned)

def test_unknown_user_still_returns_predictions():
    from backend.app.ml.recommender import recommend_for_user
    recs = recommend_for_user(user_id=999999, top_n=5)
    assert isinstance(recs, list)

def test_zero_top_n():
    from backend.app.ml.recommender import recommend_for_user
    recs = recommend_for_user(user_id=1, top_n=0)
    assert recs == []

def test_negative_top_n_safe():
    from backend.app.ml.recommender import recommend_for_user
    recs = recommend_for_user(user_id=1, top_n=-1)
    assert isinstance(recs, list)
