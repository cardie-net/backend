import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import _demote_guest_public_items, _migrate_legacy_unverified_users
from src.models.tables import (
    Deck,
    Folder,
    PendingRegistration,
    PrivacyLevel,
    User,
)


async def _insert_raw_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    email: str,
    username: str,
    *,
    is_guest: bool = False,
    is_verified: bool = False,
) -> None:
    """Insert a user row the way the app does (32-hex id, bcrypt hash)."""
    from src.auth.utils import get_password_hash

    await session.execute(
        insert(User).values(
            id=user_id,
            email=email,
            hashed_password=get_password_hash("oldpassword123"),
            is_active=True,
            is_superuser=False,
            is_verified=is_verified,
            is_guest=is_guest,
            username=username,
            display_name=username,
            email_verification_token="legacytoken1" if not is_verified else None,
        )
    )
    await session.commit()


@pytest.mark.asyncio
async def test_migration_converts_legacy_unverified_user(async_session: AsyncSession):
    user_id = uuid.uuid4()
    await _insert_raw_user(async_session, user_id, "legacy@example.com", "legacyuser")

    await _migrate_legacy_unverified_users(async_session)

    user = await async_session.get(User, user_id)
    assert user is not None  # row kept (data preserved)
    assert user.is_guest is True
    assert user.email.startswith("guest_")
    assert user.email.endswith("@guest.example.com")
    assert user.email != "legacy@example.com"
    assert user.email_verification_token is None

    pendings = (
        (await async_session.execute(select(PendingRegistration))).scalars().all()
    )
    assert len(pendings) == 1
    pending = pendings[0]
    assert pending.email == "legacy@example.com"
    assert pending.guest_user_id == user_id
    assert pending.email_verification_token == "legacytoken1"


@pytest.mark.asyncio
async def test_migration_is_idempotent(async_session: AsyncSession):
    user_id = uuid.uuid4()
    await _insert_raw_user(async_session, user_id, "legacy@example.com", "legacyuser")

    await _migrate_legacy_unverified_users(async_session)
    await _migrate_legacy_unverified_users(async_session)

    count = (
        await async_session.execute(text("SELECT COUNT(*) FROM pending_registrations"))
    ).scalar()
    assert count == 1


@pytest.mark.asyncio
async def test_migration_skips_verified_and_guest_users(async_session: AsyncSession):
    real_id = uuid.uuid4()
    guest_id = uuid.uuid4()
    await _insert_raw_user(
        async_session, real_id, "real@example.com", "realuser", is_verified=True
    )
    await _insert_raw_user(
        async_session, guest_id, "guest_x@guest.example.com", "guestx", is_guest=True
    )

    await _migrate_legacy_unverified_users(async_session)

    count = (
        await async_session.execute(text("SELECT COUNT(*) FROM pending_registrations"))
    ).scalar()
    assert count == 0

    real = await async_session.get(User, real_id)
    guest = await async_session.get(User, guest_id)
    assert real.email == "real@example.com"
    assert real.is_guest is False
    assert guest.is_guest is True


@pytest.mark.asyncio
async def test_demote_guest_public_items(async_session: AsyncSession):
    guest_id = uuid.uuid4()
    real_id = uuid.uuid4()
    await _insert_raw_user(
        async_session, guest_id, "guest_y@guest.example.com", "guesty", is_guest=True
    )
    await _insert_raw_user(
        async_session,
        real_id,
        "real2@example.com",
        "realuser2",
        is_guest=False,
        is_verified=True,
    )

    guest_public_deck = Deck(
        name="Guest Public Deck",
        slug="guest-public-deck",
        privacy=PrivacyLevel.PUBLIC,
        user_id=guest_id,
    )
    guest_unlisted_folder = Folder(
        name="Guest Unlisted Folder",
        slug="guest-unlisted-folder",
        privacy=PrivacyLevel.UNLISTED,
        user_id=guest_id,
    )
    guest_private_deck = Deck(
        name="Guest Private Deck",
        slug="guest-private-deck",
        privacy=PrivacyLevel.PRIVATE,
        user_id=guest_id,
    )
    real_public_deck = Deck(
        name="Real Public Deck",
        slug="real-public-deck",
        privacy=PrivacyLevel.PUBLIC,
        user_id=real_id,
    )
    async_session.add_all(
        [guest_public_deck, guest_unlisted_folder, guest_private_deck, real_public_deck]
    )
    await async_session.commit()

    await _demote_guest_public_items(async_session)

    assert (
        await async_session.get(Deck, guest_public_deck.id)
    ).privacy == PrivacyLevel.PRIVATE
    assert (
        await async_session.get(Folder, guest_unlisted_folder.id)
    ).privacy == PrivacyLevel.PRIVATE
    # Already-private items and non-guest owners are untouched
    assert (
        await async_session.get(Deck, guest_private_deck.id)
    ).privacy == PrivacyLevel.PRIVATE
    assert (
        await async_session.get(Deck, real_public_deck.id)
    ).privacy == PrivacyLevel.PUBLIC


@pytest.mark.asyncio
async def test_startup_migration_demotes_guest_items_via_api(
    async_client: AsyncClient, async_session: AsyncSession
):
    """Guest content created before the API guard existed gets demoted by the startup migration."""
    from sqlalchemy import update as sa_update

    from src.database import _demote_guest_public_items
    from src.models.tables import Deck as DeckModel

    guest_resp = await async_client.post("/api/v1/auth/guest")
    guest_cookie = {"X-Test-Cookie": guest_resp.cookies.get("cardie_session")}

    # Create a private deck through the normal API...
    deck_resp = await async_client.post(
        "/api/v1/decks",
        json={"name": "Legacy Public", "slug": "legacy-public"},
        headers=guest_cookie,
    )
    assert deck_resp.status_code == 200
    deck_id = uuid.UUID(deck_resp.json()["id"])

    # ...then simulate pre-existing data by setting it public behind the guard's back
    await async_session.execute(
        sa_update(DeckModel)
        .where(DeckModel.id == deck_id)
        .values(privacy=PrivacyLevel.PUBLIC)
    )
    await async_session.commit()
    async_session.expire_all()

    get_resp = await async_client.get(f"/api/v1/decks/{deck_id}", headers=guest_cookie)
    assert get_resp.json()["privacy"] == "public"

    await _demote_guest_public_items(async_session)

    get_resp = await async_client.get(f"/api/v1/decks/{deck_id}", headers=guest_cookie)
    assert get_resp.json()["privacy"] == "private"
