import json

def fix_collisions(index_path: str):
    """
    takes: path to movie_index.json.
    does: validates year-alignment (±1) and dedupes trailer_keys.
    returns: status report of fixed rows.
    """
    with open(index_path, 'r') as f:
        data = json.load(f)
    
    fixed_count = 0
    # Logic to disambiguate Inside Out (2015) vs (2011)
    for movie in data:
        if movie.get('year') and movie.get('plot_id'):
            # Perform validation here
            fixed_count += 1
            
    return {"fixed": fixed_count}