import uuid

import sqlalchemy.exc
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from .. import crud, models
from ..auth.router import current_active_user
from ..database import get_db

router = APIRouter(prefix="/decks", tags=["decks"])


@router.post("", response_model=models.DeckRead)
async def create_deck(
    deck: models.DeckCreate,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> models.DeckRead:
    """Create a new deck for the current user."""
    if deck.folder_id is not None:
        folder = await crud.get_folder(db, folder_id=deck.folder_id)
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        if folder.user_id != user.id:
            raise HTTPException(status_code=403, detail="Not enough permissions")

    try:
        return await crud.create_deck_for_user(db=db, deck=deck, user_id=user.id)
    except sqlalchemy.exc.IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=400, detail="Deck with this slug already exists"
        ) from exc


@router.get("/{deck_id}", response_model=models.DeckRead)
async def get_deck(
    deck_id: uuid.UUID,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> models.DeckRead:
    """Retrieve a specific deck by its ID."""
    db_deck = await crud.get_deck(db, deck_id=deck_id)
    if not db_deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    if db_deck.user_id != user.id and db_deck.privacy == models.PrivacyLevel.PRIVATE:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    return db_deck


@router.delete("/{deck_id}", status_code=204)
async def delete_deck(
    deck_id: uuid.UUID,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a specific deck."""
    db_deck = await crud.get_deck(db, deck_id=deck_id)
    if not db_deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    if db_deck.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    await crud.delete_deck(db=db, db_deck=db_deck)
    return None


@router.patch("/{deck_id}", response_model=models.DeckRead)
async def update_deck(
    deck_id: uuid.UUID,
    deck_update: models.DeckUpdate,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> models.DeckRead:
    """Update properties of a specific deck."""
    db_deck = await crud.get_deck(db, deck_id=deck_id)
    if not db_deck:
        raise HTTPException(status_code=404, detail="Deck not found")
    if db_deck.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    if deck_update.folder_id is not None:
        folder = await crud.get_folder(db, folder_id=deck_update.folder_id)
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
        if folder.user_id != user.id:
            raise HTTPException(status_code=403, detail="Not enough permissions")

    try:
        return await crud.update_deck(db=db, db_deck=db_deck, deck_update=deck_update)
    except sqlalchemy.exc.IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=400, detail="Deck with this slug already exists"
        ) from exc


@router.get("/{deck_id}/progress", response_model=list[models.CardProgressRead])
async def get_deck_progress(
    deck_id: uuid.UUID,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> list[models.CardProgressRead]:
    """Retrieve learning progress for a specific deck."""
    db_deck = await crud.get_deck(db, deck_id=deck_id)
    if not db_deck:
        raise HTTPException(status_code=404, detail="Deck not found")

    # Allow reading progress even if the deck is public, as progress is tied to the current user
    if db_deck.user_id != user.id and db_deck.privacy == models.PrivacyLevel.PRIVATE:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    return await crud.get_deck_progress(db, user_id=user.id, deck_id=deck_id)


@router.post("/{deck_id}/progress", status_code=204)
async def sync_deck_progress(
    deck_id: uuid.UUID,
    sync_request: models.CardProgressSyncRequest,
    user: models.User = Depends(current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Sync learning progress for a specific deck."""
    db_deck = await crud.get_deck(db, deck_id=deck_id)
    if not db_deck:
        raise HTTPException(status_code=404, detail="Deck not found")

    if db_deck.user_id != user.id and db_deck.privacy == models.PrivacyLevel.PRIVATE:
        raise HTTPException(status_code=403, detail="Not enough permissions")

    await crud.sync_deck_progress(
        db, user_id=user.id, deck_id=deck_id, progress_updates=sync_request.progress
    )
