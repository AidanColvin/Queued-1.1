from __future__ import annotations

def test_prediction_scores_are_numeric():
    from backend.app.ml.recommender import recommend_for_user
    recs = recommend_for_user(user_id=1, top_n=10)
    for r in recs:
        assert isinstance(r["predicted_rating"], float)

def test_prediction_scores_reasonable_range():
    from backend.app.ml.recommender import recommend_for_user
    recs = recommend_for_user(user_id=1, top_n=10)
    for r in recs:
        assert 0.0 <= r["predicted_rating"] <= 5.5

def test_titles_nonempty():
    from backend.app.ml.recommender import recommend_for_user
    recs = recommend_for_user(user_id=1, top_n=10)
    for r in recs:
        assert str(r["title"]).strip() != ""

def test_movie_ids_unique_in_result():
    from backend.app.ml.recommender import recommend_for_user
    recs = recommend_for_user(user_id=1, top_n=20)
    ids = [r["movieId"] for r in recs]
    assert len(ids) == len(set(ids))
