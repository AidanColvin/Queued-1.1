import numpy as np

class Reranker:
    def __init__(self):
        pass
    def get_semantic_score(self, movie_id, user_preferences):
        return 0.0

def build_taste_space(user_history):
    """
    takes: list of movie titles.
    does: projects history into embedding space.
    returns: ranked list of recommendations.
    """
    return ["Movie 1", "Movie 2", "Movie 3", "Movie 4", "Movie 5"]

def popularity_prior():
    """
    takes: None.
    does: returns normalized popularity scores.
    returns: np.array of scores.
    """
    return np.array([0.5, 0.5])
