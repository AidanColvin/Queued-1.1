import numpy as np
import os

class SessionStore:
    def __init__(self):
        self.dim = 384
        weight_path = "backend/ml/artifacts/prod_weights.npy"
        if os.path.exists(weight_path):
            self._embeddings = np.load(weight_path)
        else:
            self._embeddings = np.random.rand(100, self.dim)

    def get_semantic_score(self, movie_id, user_preferences):
        """
        # Takes: movie_id (int), user_preferences (array)
        # Does: Calculates dot product of the last 5 injected dimensions
        # Returns: float (semantic relevance score)
        """
        if movie_id < len(self._embeddings):
            movie_tags = self._embeddings[movie_id, -5:] 
            return np.dot(movie_tags, user_preferences)
        return 0.0
