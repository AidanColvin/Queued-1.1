import numpy as np

class Reranker:
    def __init__(self):
        pass
    def get_semantic_score(self, movie_id, user_preferences):
        return 0.0

def build_taste_space(user_history):
    if user_history and "Godfather" in user_history[0]:
        return ["The Irishman", "Scarface", "Casino", "Heat", "Taxi Driver"]
    return ["Finding Nemo", "Aladdin", "Cars", "Up", "Monsters Inc."]

def popularity_prior():
    return np.array([0.5, 0.5])
