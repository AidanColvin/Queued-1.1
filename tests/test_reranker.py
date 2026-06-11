import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../backend')))
from ml.reranker import build_taste_space

def test_reranker_logic():
    # Test Godfather trigger
    recs = build_taste_space(["The Godfather"])
    assert "The Irishman" in recs
    # Test default
    recs = build_taste_space(["Unknown Movie"])
    assert len(recs) == 5
