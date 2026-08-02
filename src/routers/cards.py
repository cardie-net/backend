import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud, models
from ..auth.router import current_active_user
from ..database import get_db
from ..services.image_service import collect_image_urls
from ..services.s3_service import CARD_IMAGE_PREFIX, delete_managed_images

router = APIRouter(prefix="/decks/{deck_id}/cards", tags=["cards"])


@router.get("", response_model=list[models.CardRead])
async def read_cards(
    deck_id: uuid.UUID,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[models.CardRead]:
    """Retrieve all cards for a specific deck."""
    deck = await crud.get_deck(db, deck_id=deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    if deck.user_id != user.id and deck.privacy == models.PrivacyLevel.PRIVATE:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return await crud.get_cards_for_deck(db, deck_id=deck_id)


@router.post("", response_model=models.CardRead)
async def create_card(
    deck_id: uuid.UUID,
    card: models.CardCreate,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> models.CardRead:
    """Create a new card within a specific deck."""
    deck = await crud.get_deck(db, deck_id=deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    if deck.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return await crud.create_card_for_deck(db=db, card=card, deck_id=deck_id)


@router.delete("/{card_id}", status_code=204)
async def delete_card(
    deck_id: uuid.UUID,
    card_id: uuid.UUID,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a specific card from a deck."""
    deck = await crud.get_deck(db, deck_id=deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    if deck.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    card = await crud.get_card(db, card_id=card_id)
    if not card or card.deck_id != deck_id:
        raise HTTPException(status_code=404, detail="Card not found")

    urls = collect_image_urls(card.front, card.back)
    await crud.delete_card(db, db_card=card)

    if urls:
        await asyncio.to_thread(
            delete_managed_images, urls, f"{CARD_IMAGE_PREFIX}{user.id}/"
        )


@router.patch("/{card_id}", response_model=models.CardRead)
async def update_card(
    deck_id: uuid.UUID,
    card_id: uuid.UUID,
    card_update: models.CardUpdate,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> models.CardRead:
    """Update properties of a specific card."""
    deck = await crud.get_deck(db, deck_id=deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    if deck.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    card = await crud.get_card(db, card_id=card_id)
    if not card or card.deck_id != deck_id:
        raise HTTPException(status_code=404, detail="Card not found")

    # Diff old vs new image URLs; delete S3 objects for managed images removed
    # from the card (after a successful commit, so a DB failure leaves them intact)
    old_urls = set(collect_image_urls(card.front, card.back))
    new_front = card_update.front if card_update.front is not None else card.front
    new_back = card_update.back if card_update.back is not None else card.back
    removed_urls = old_urls - set(collect_image_urls(new_front, new_back))

    updated = await crud.update_card(db, db_card=card, card_update=card_update)

    if removed_urls:
        await asyncio.to_thread(
            delete_managed_images,
            list(removed_urls),
            f"{CARD_IMAGE_PREFIX}{user.id}/",
        )

    return updated


@router.post("/reorder")
async def reorder_cards(
    deck_id: uuid.UUID,
    reorder: models.CardReorder,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Reorder the cards within a specific deck."""
    deck = await crud.get_deck(db, deck_id=deck_id)
    if not deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    if deck.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    current_cards = await crud.get_cards_for_deck(db, deck_id=deck_id)
    current_card_ids = {c.id for c in current_cards}

    if len(reorder.card_ids) != len(set(reorder.card_ids)):
        raise HTTPException(status_code=400, detail="Duplicate card IDs provided")

    if set(reorder.card_ids) != current_card_ids:
        raise HTTPException(
            status_code=400,
            detail="Provided card IDs do not match the deck's cards exactly",
        )

    await crud.reorder_cards(db, deck_id=deck_id, card_ids=reorder.card_ids)
    return {"status": "ok"}
