from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from db.models_v3 import UserProfileExtension

def process_daily_engagement(db: Session, profile: UserProfileExtension) -> dict:
    """
    # Takes: SQLAlchemy database session, current UserProfileExtension row.
    # Does: Validates timeline delta, updates streak/freeze states, and processes level-ups.
    # Returns: Dict containing updated metrics (streak, xp_gained, leveled_up, current_level).
    """
    now = datetime.utcnow()
    today = now.date()
    last_active = profile.last_active_date.date()
    
    xp_gained = 10
    leveled_up = False
    
    if last_active == today:
        profile.experience_points += xp_gained
    elif last_active == today - timedelta(days=1):
        profile.current_streak += 1
        if profile.current_streak > profile.longest_streak:
            profile.longest_streak = profile.current_streak
        
        streak_bonus = min(profile.current_streak * 2, 50)
        xp_gained += streak_bonus
        profile.experience_points += xp_gained
        profile.last_active_date = now
    else:
        days_missed = (today - last_active).days
        if days_missed == 2 and profile.streak_freezes_available > 0:
            profile.streak_freezes_available -= 1
            profile.current_streak += 1
            profile.last_active_date = now
        else:
            profile.current_streak = 0
            profile.last_active_date = now
            profile.experience_points += xp_gained

    next_level_threshold = profile.current_level * 100
    if profile.experience_points >= next_level_threshold:
        profile.current_level += 1
        leveled_up = True
        if profile.current_level % 5 == 0:
            profile.streak_freezes_available += 1
            
    db.commit()
    return {
        "current_streak": profile.current_streak,
        "xp_gained": xp_gained,
        "leveled_up": leveled_up,
        "current_level": profile.current_level
    }
