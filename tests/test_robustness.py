# tests/test_robustness.py
import pytest
import numpy as np
from ml.reranker import build_taste_space, popularity_prior

def test_reranker_predicts_diverse_tastes():
    """
    takes: model artifacts (embeddings.npy).
    does: tests if the reranker adapts output based on different user history inputs.
    returns: assertion error if recommendation order is identical for different user profiles.
    """
    # 1. Simulate two users with opposite tastes
    user_a_history = ["The Godfather", "Goodfellas"]
    user_b_history = ["The Little Mermaid", "Toy Story"]
    
    # 2. Get recommendations
    recs_a = build_taste_space(user_a_history)
    recs_b = build_taste_space(user_b_history)
    
    # 3. Assert diversity
    # The models must recommend different films for different tastes
    assert recs_a[0] != recs_b[0], "Reranker failed to adapt to diverse tastes"
    assert len(recs_a) == 5, "Reranker must return 5 candidates"

def test_popularity_prior_bounds():
    """
    takes: model artifacts.
    does: ensures the popularity prior probability is normalized between 0 and 1.
    returns: assertion error if weights are invalid.
    """
    priors = popularity_prior()
    assert np.all((priors >= 0) & (priors <= 1)), "Priors must be in [0, 1]"