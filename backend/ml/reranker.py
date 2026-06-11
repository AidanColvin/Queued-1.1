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