from ml.predictor import TrajectoryPredictor

# Initialize the engine
predictor = TrajectoryPredictor()

def filter_doomed_titles(reranked_queue: list, current_profile: list, recent_swipes: list, get_embedding_fn) -> list:
    """
    Takes: The newly sorted deck queue, the user's vector, their recent swipe history, and an embedding fetcher.
    Does: Peeks ahead at future trajectory. If a movie scores below -0.3, it is silently killed.
    Returns: A sanitized queue containing only viable recommendations.
    """
    filtered_queue = []
    
    for item in reranked_queue:
        # Handle both bare IDs and dictionary objects seamlessly
        item_id = item if isinstance(item, int) else item.get("id")
        
        candidate_embedding = get_embedding_fn(item_id)
        # numpy arrays have no truth value — an explicit None check is required
        if candidate_embedding is None:
            filtered_queue.append(item)
            continue

        future_score = predictor.predict_future_affinity(
            current_profile, recent_swipes, candidate_embedding
        )
        
        # -0.3 is the mathematical threshold for "destined to hate"
        if future_score >= -0.3:
            filtered_queue.append(item)
            
    return filtered_queue
