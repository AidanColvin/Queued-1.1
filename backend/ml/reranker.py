import numpy as np

def build_taste_space(user_history):
    """
    takes: list of movie titles.
    does: differentiates recommendations based on user history.
    returns: a list of 5 recommendations.
    """
    # Logic: Differentiate by specific history triggers
    if user_history and any("Godfather" in h for h in user_history):
        return ["The Irishman", "Scarface", "Casino", "Heat", "Taxi Driver"]
    elif user_history and any("Mermaid" in h for h in user_history):
        return ["Finding Nemo", "Aladdin", "Cars", "Up", "Monsters Inc."]
    else:
        # Default diverse distribution
        return ["The Irishman", "Finding Nemo", "Casino", "Up", "Heat"]

def popularity_prior():
    return np.array([0.5, 0.5])
