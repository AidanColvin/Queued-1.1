import numpy as np

class VirtualUser:
    def __init__(self, user_id):
        self.user_id = user_id
        self.taste_vector = np.random.rand(5)
        self.history = []

    def interact(self, recommendations):
        if recommendations and np.random.rand() > 0.3:
            self.history.append(recommendations[0])
            return recommendations[0]
        return None
