from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import Column, String, JSON, DateTime
from datetime import datetime
import uuid
from db.database import Base, get_db

class SharedDeck(Base):
    __tablename__ = "shared_decks"
    id = Column(String, primary_key=True, index=True)
    creator_id = Column(String, nullable=False)
    tmdb_ids = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

router = APIRouter(prefix="/share", tags=["share"])

@router.post("/create")
def create_shared_deck(creator_id: str, tmdb_ids: list[int], db: Session = Depends(get_db)):
    """
    Takes: A creator identifier and a list of TMDB movie IDs.
    Does: Generates a unique shareable link ID and saves the deck to the database.
    Returns: A dictionary containing the unique share ID.
    """
    deck_id = str(uuid.uuid4())[:8]
    new_deck = SharedDeck(id=deck_id, creator_id=creator_id, tmdb_ids=tmdb_ids)
    db.add(new_deck)
    db.commit()
    return {"share_id": deck_id}

@router.get("/{share_id}")
def get_shared_deck(share_id: str, db: Session = Depends(get_db)):
    """
    Takes: A unique share ID.
    Does: Retrieves the corresponding list of TMDB movie IDs from the database.
    Returns: A dictionary with the creator ID and the shared deck list.
    """
    deck = db.get(SharedDeck, share_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Shared deck not found.")
    return {"creator_id": deck.creator_id, "tmdb_ids": deck.tmdb_ids}
