from __future__ import annotations

def test_load_model_cached_identity():
    from backend.app.ml.recommender import load_model
    a = load_model()
    b = load_model()
    assert a is b

def test_load_movies_cached_identity():
    from backend.app.ml.recommender import load_movies
    a = load_movies()
    b = load_movies()
    assert a is b

def test_load_ratings_cached_identity():
    from backend.app.ml.recommender import load_ratings
    a = load_ratings()
    b = load_ratings()
    assert a is b
