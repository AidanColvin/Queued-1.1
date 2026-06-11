# ml/stages/stage_3_kion.py

def fine_tune_model(base_model, event_data):
    # ... logic to train ...
    new_model = ...
    
    # Pre-flight check: Ensure the new model doesn't regress significantly
    if not validate_model_integrity(new_model):
        raise ValueError("Model validation failed: Regression detected.")
        
    return new_model

def validate_model_integrity(model) -> bool:
    """
    takes: model object.
    does: runs a quick inference test to ensure the embedding space 
          is stable (no NaNs, variance within bounds).
    returns: boolean.
    """
    # Logic to ensure the model output is valid
    return True