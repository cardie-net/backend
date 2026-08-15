import difflib
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import func, select

from .. import models


def calculate_fuzzy_match_score(
    query: str,
    name: str,
    description: str | None,
    username: str,
    display_name: str,
) -> float:
    """Calculate fuzzy similarity score between a query and an item."""
    q = query.strip().lower()
    if not q:
        return 1.0

    name_lower = (name or "").lower()
    desc_lower = (description or "").lower()
    user_lower = (username or "").lower()
    disp_lower = (display_name or "").lower()

    if q == name_lower:
        return 1.0
    if q in name_lower:
        return 0.95
    if q == user_lower or q == disp_lower:
        return 0.9
    if q in user_lower or q in disp_lower:
        return 0.85
    if desc_lower and q in desc_lower:
        return 0.8

    scores: list[float] = []

    # Sequence matcher on full fields
    scores.append(difflib.SequenceMatcher(None, q, name_lower).ratio() * 0.9)
    scores.append(difflib.SequenceMatcher(None, q, user_lower).ratio() * 0.8)
    scores.append(difflib.SequenceMatcher(None, q, disp_lower).ratio() * 0.8)

    # Word-level matching for name
    for word in name_lower.split():
        scores.append(difflib.SequenceMatcher(None, q, word).ratio() * 0.88)

    # Word-level matching for display name
    for word in disp_lower.split():
        scores.append(difflib.SequenceMatcher(None, q, word).ratio() * 0.78)

    # Word-level matching for description
    if desc_lower:
        for word in desc_lower.split():
            scores.append(difflib.SequenceMatcher(None, q, word).ratio() * 0.7)

    return max(scores) if scores else 0.0


async def get_user_starred_id_sets(
    db: AsyncSession, user_id: uuid.UUID | None
) -> tuple[set[uuid.UUID], set[uuid.UUID]]:
    """Retrieve sets of starred deck IDs and folder IDs for a user."""
    if not user_id:
        return set(), set()

    deck_stars_stmt = select(models.DeckStar.deck_id).where(
        models.DeckStar.user_id == user_id
    )
    folder_stars_stmt = select(models.FolderStar.folder_id).where(
        models.FolderStar.user_id == user_id
    )

    deck_res = await db.execute(deck_stars_stmt)
    folder_res = await db.execute(folder_stars_stmt)

    starred_deck_ids = set(deck_res.scalars().all())
    starred_folder_ids = set(folder_res.scalars().all())
    return starred_deck_ids, starred_folder_ids


async def get_community_items(
    db: AsyncSession,
    current_user_id: uuid.UUID | None = None,
    item_type: str = "all",
    sort: str = "popular",
    query: str | None = None,
    page: int = 1,
    limit: int = 20,
    threshold: float = 0.6,
) -> tuple[list[dict[str, Any]], int]:
    """Retrieve public community items with sorting, fuzzy search, and pagination."""
    starred_deck_ids, starred_folder_ids = await get_user_starred_id_sets(
        db, current_user_id
    )
    items: list[dict[str, Any]] = []

    # Fetch public decks if requested
    if item_type in ("all", "deck"):
        deck_stmt = (
            select(models.Deck)
            .where(models.Deck.privacy == models.PrivacyLevel.PUBLIC)
            .options(selectinload(models.Deck.owner))
        )
        deck_res = await db.execute(deck_stmt)
        decks = deck_res.scalars().all()

        for d in decks:
            owner = d.owner
            owner_dict = {
                "id": owner.id if owner else d.user_id,
                "username": owner.username if owner else "unknown",
                "display_name": owner.display_name if owner else "Unknown",
                "avatar_url": owner.avatar_url if owner else None,
            }
            props = d.properties or {}
            items.append(
                {
                    "id": d.id,
                    "name": d.name,
                    "slug": d.slug,
                    "privacy": d.privacy,
                    "user_id": d.user_id,
                    "folder_id": d.folder_id,
                    "properties": d.properties,
                    "type": "deck",
                    "cards_count": getattr(d, "cards_count", 0) or 0,
                    "stars_count": getattr(d, "stars_count", 0) or 0,
                    "is_starred": d.id in starred_deck_ids,
                    "created_at": d.created_at,
                    "updated_at": d.updated_at,
                    "owner": owner_dict,
                    "_desc": props.get("description", ""),
                }
            )

    # Fetch public folders if requested
    if item_type in ("all", "folder"):
        folder_stmt = (
            select(models.Folder)
            .where(models.Folder.privacy == models.PrivacyLevel.PUBLIC)
            .options(selectinload(models.Folder.owner))
        )
        folder_res = await db.execute(folder_stmt)
        folders = folder_res.scalars().all()

        for f in folders:
            owner = f.owner
            owner_dict = {
                "id": owner.id if owner else f.user_id,
                "username": owner.username if owner else "unknown",
                "display_name": owner.display_name if owner else "Unknown",
                "avatar_url": owner.avatar_url if owner else None,
            }
            props = f.properties or {}
            items.append(
                {
                    "id": f.id,
                    "name": f.name,
                    "slug": f.slug,
                    "privacy": f.privacy,
                    "user_id": f.user_id,
                    "parent_id": f.parent_id,
                    "properties": f.properties,
                    "type": "folder",
                    "decks_count": getattr(f, "decks_count", 0) or 0,
                    "stars_count": getattr(f, "stars_count", 0) or 0,
                    "is_starred": f.id in starred_folder_ids,
                    "created_at": f.created_at,
                    "updated_at": f.updated_at,
                    "owner": owner_dict,
                    "_desc": props.get("description", ""),
                }
            )

    # Filter by fuzzy search if query is provided or sort is search
    if query and query.strip():
        scored_items = []
        for it in items:
            owner = it["owner"]
            score = calculate_fuzzy_match_score(
                query=query,
                name=it["name"],
                description=it.get("_desc"),
                username=owner.get("username", ""),
                display_name=owner.get("display_name", ""),
            )
            if score >= threshold:
                it["_score"] = score
                scored_items.append(it)

        # Sort by match score DESC, stars_count DESC, created_at DESC
        scored_items.sort(
            key=lambda x: (
                x.get("_score", 0.0),
                x.get("stars_count", 0),
                x.get("created_at"),
            ),
            reverse=True,
        )
        items = scored_items
    else:
        if sort == "created":
            items.sort(key=lambda x: x.get("created_at"), reverse=True)
        elif sort == "updated":
            items.sort(key=lambda x: x.get("updated_at"), reverse=True)
        else:  # popular
            items.sort(
                key=lambda x: (x.get("stars_count", 0), x.get("created_at")),
                reverse=True,
            )

    total = len(items)
    start = (page - 1) * limit
    end = start + limit
    page_items = items[start:end]

    # Clean internal helper fields
    for it in page_items:
        it.pop("_desc", None)
        it.pop("_score", None)

    return page_items, total


async def star_deck(
    db: AsyncSession, user_id: uuid.UUID, deck_id: uuid.UUID
) -> tuple[bool, int]:
    """Star a deck and return the updated star status and star count."""
    deck = await db.get(models.Deck, deck_id)
    if not deck:
        raise ValueError("Deck not found")
    if deck.user_id == user_id:
        raise ValueError("Cannot star your own deck")

    existing_star = await db.execute(
        select(models.DeckStar).where(
            models.DeckStar.user_id == user_id, models.DeckStar.deck_id == deck_id
        )
    )
    if not existing_star.scalars().first():
        new_star = models.DeckStar(user_id=user_id, deck_id=deck_id)
        db.add(new_star)
        await db.commit()

    count_res = await db.execute(
        select(func.count(models.DeckStar.id)).where(models.DeckStar.deck_id == deck_id)
    )
    stars_count = count_res.scalar() or 0
    return True, stars_count


async def unstar_deck(
    db: AsyncSession, user_id: uuid.UUID, deck_id: uuid.UUID
) -> tuple[bool, int]:
    """Unstar a deck and return the updated star status and star count."""
    deck = await db.get(models.Deck, deck_id)
    if not deck:
        raise ValueError("Deck not found")

    existing_star = await db.execute(
        select(models.DeckStar).where(
            models.DeckStar.user_id == user_id, models.DeckStar.deck_id == deck_id
        )
    )
    star_obj = existing_star.scalars().first()
    if star_obj:
        await db.delete(star_obj)
        await db.commit()

    count_res = await db.execute(
        select(func.count(models.DeckStar.id)).where(models.DeckStar.deck_id == deck_id)
    )
    stars_count = count_res.scalar() or 0
    return False, stars_count


async def star_folder(
    db: AsyncSession, user_id: uuid.UUID, folder_id: uuid.UUID
) -> tuple[bool, int]:
    """Star a folder and return the updated star status and star count."""
    folder = await db.get(models.Folder, folder_id)
    if not folder:
        raise ValueError("Folder not found")
    if folder.user_id == user_id:
        raise ValueError("Cannot star your own folder")

    existing_star = await db.execute(
        select(models.FolderStar).where(
            models.FolderStar.user_id == user_id,
            models.FolderStar.folder_id == folder_id,
        )
    )
    if not existing_star.scalars().first():
        new_star = models.FolderStar(user_id=user_id, folder_id=folder_id)
        db.add(new_star)
        await db.commit()

    count_res = await db.execute(
        select(func.count(models.FolderStar.id)).where(
            models.FolderStar.folder_id == folder_id
        )
    )
    stars_count = count_res.scalar() or 0
    return True, stars_count


async def unstar_folder(
    db: AsyncSession, user_id: uuid.UUID, folder_id: uuid.UUID
) -> tuple[bool, int]:
    """Unstar a folder and return the updated star status and star count."""
    folder = await db.get(models.Folder, folder_id)
    if not folder:
        raise ValueError("Folder not found")

    existing_star = await db.execute(
        select(models.FolderStar).where(
            models.FolderStar.user_id == user_id,
            models.FolderStar.folder_id == folder_id,
        )
    )
    star_obj = existing_star.scalars().first()
    if star_obj:
        await db.delete(star_obj)
        await db.commit()

    count_res = await db.execute(
        select(func.count(models.FolderStar.id)).where(
            models.FolderStar.folder_id == folder_id
        )
    )
    stars_count = count_res.scalar() or 0
    return False, stars_count


async def get_user_starred_ids(
    db: AsyncSession, user_id: uuid.UUID
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """Retrieve all starred deck IDs and folder IDs for a user."""
    deck_stars_stmt = select(models.DeckStar.deck_id).where(
        models.DeckStar.user_id == user_id
    )
    folder_stars_stmt = select(models.FolderStar.folder_id).where(
        models.FolderStar.user_id == user_id
    )

    deck_res = await db.execute(deck_stars_stmt)
    folder_res = await db.execute(folder_stars_stmt)

    return list(deck_res.scalars().all()), list(folder_res.scalars().all())


async def get_user_favorite_items(
    db: AsyncSession, user_id: uuid.UUID
) -> list[dict[str, Any]]:
    """Retrieve all starred public and accessible decks and folders for a user."""
    items: list[dict[str, Any]] = []

    # Get starred decks with DeckStar join
    deck_stmt = (
        select(models.Deck, models.DeckStar.created_at.label("starred_at"))
        .join(models.DeckStar, models.DeckStar.deck_id == models.Deck.id)
        .where(
            models.DeckStar.user_id == user_id,
            (models.Deck.privacy == models.PrivacyLevel.PUBLIC)
            | (models.Deck.user_id == user_id),
        )
        .options(selectinload(models.Deck.owner))
        .order_by(models.DeckStar.created_at.desc())
    )
    deck_res = await db.execute(deck_stmt)
    for d, starred_at in deck_res.all():
        owner = d.owner
        owner_dict = {
            "id": owner.id if owner else d.user_id,
            "username": owner.username if owner else "unknown",
            "display_name": owner.display_name if owner else "Unknown",
            "avatar_url": owner.avatar_url if owner else None,
        }
        items.append(
            {
                "id": d.id,
                "name": d.name,
                "slug": d.slug,
                "privacy": d.privacy,
                "user_id": d.user_id,
                "folder_id": d.folder_id,
                "properties": d.properties,
                "type": "deck",
                "cards_count": getattr(d, "cards_count", 0) or 0,
                "stars_count": getattr(d, "stars_count", 0) or 0,
                "is_starred": True,
                "created_at": d.created_at,
                "updated_at": d.updated_at,
                "owner": owner_dict,
                "_starred_at": starred_at,
            }
        )

    # Get starred folders with FolderStar join
    folder_stmt = (
        select(models.Folder, models.FolderStar.created_at.label("starred_at"))
        .join(models.FolderStar, models.FolderStar.folder_id == models.Folder.id)
        .where(
            models.FolderStar.user_id == user_id,
            (models.Folder.privacy == models.PrivacyLevel.PUBLIC)
            | (models.Folder.user_id == user_id),
        )
        .options(selectinload(models.Folder.owner))
        .order_by(models.FolderStar.created_at.desc())
    )
    folder_res = await db.execute(folder_stmt)
    for f, starred_at in folder_res.all():
        owner = f.owner
        owner_dict = {
            "id": owner.id if owner else f.user_id,
            "username": owner.username if owner else "unknown",
            "display_name": owner.display_name if owner else "Unknown",
            "avatar_url": owner.avatar_url if owner else None,
        }
        items.append(
            {
                "id": f.id,
                "name": f.name,
                "slug": f.slug,
                "privacy": f.privacy,
                "user_id": f.user_id,
                "parent_id": f.parent_id,
                "properties": f.properties,
                "type": "folder",
                "decks_count": getattr(f, "decks_count", 0) or 0,
                "stars_count": getattr(f, "stars_count", 0) or 0,
                "is_starred": True,
                "created_at": f.created_at,
                "updated_at": f.updated_at,
                "owner": owner_dict,
                "_starred_at": starred_at,
            }
        )

    # Sort all favorites by starred timestamp descending
    items.sort(
        key=lambda x: (
            x.get("_starred_at") or x.get("created_at"),
            x.get("created_at"),
        ),
        reverse=True,
    )
    return items
