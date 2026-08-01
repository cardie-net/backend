import uuid
from datetime import date
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth.router import current_active_user
from ..crud.deck import get_deck
from ..crud.srs import get_srs_counts_for_user, get_srs_study_cards, process_srs_reviews
from ..database import get_db
from ..models import SRSDeckCounts, SRSReviewRequest, SRSStudyResponse, User

router = APIRouter(tags=["srs"])


@router.get("/srs/counts", response_model=Dict[uuid.UUID, SRSDeckCounts])
async def get_srs_counts(
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Get SRS counts for all user decks."""
    return await get_srs_counts_for_user(db, user.id)


@router.get("/decks/{deck_id}/srs/study", response_model=SRSStudyResponse)
async def get_srs_study(
    deck_id: uuid.UUID,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Fetch cards ready for SRS study."""
    deck = await get_deck(db, deck_id)
    if not deck or deck.user_id != user.id:
        raise HTTPException(status_code=404, detail="Deck not found")

    today = date.today().isoformat()
    return await get_srs_study_cards(db, user.id, deck_id, today)


@router.post("/decks/{deck_id}/srs/review", status_code=204)
async def post_srs_review(
    deck_id: uuid.UUID,
    request: SRSReviewRequest,
    user: User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit batch of card ratings."""
    deck = await get_deck(db, deck_id)
    if not deck or deck.user_id != user.id:
        raise HTTPException(status_code=404, detail="Deck not found")

    today = date.today().isoformat()
    await process_srs_reviews(db, user.id, deck_id, request.reviews, today)
